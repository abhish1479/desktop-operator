# apps/worker/browser_actions.py
from __future__ import annotations
import os, re, time, json, asyncio, pathlib, hashlib
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Download, Locator, Page
from .browser import _get_ctx, _get_page  # uses your existing async Playwright ctx/page

# ---------- utils ----------
def _now() -> str:
    import datetime as _dt
    return _dt.datetime.now().strftime("%H:%M:%S")

def _log(lines: List[str], msg: str):
    lines.append(f"[{_now()}] {msg}")

def _mask(v: Any) -> Any:
    if isinstance(v, str):
        # mask typical password tokens
        if re.search(r"(pass(word)?|pwd|otp|code)\s*[:=]", v, re.I):
            return re.sub(r"(:\s*)(\S+)", r"\1***", v)
        if len(v) >= 3 and ("@" not in v) and (any(c.isdigit() for c in v)) and (any(c.isalpha() for c in v)):
            # simple heuristic: long-ish token-like => mask
            return "***"
    return v

def _safe_join(base_dir: str, name: str) -> str:
    base = pathlib.Path(base_dir).resolve()
    target = (base / name).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("path_traversal_blocked")
    return str(target)

def _profile_path(hint: Optional[str]) -> str:
    if not hint:
        return "data/playwright-profiles/default"
    if os.path.isabs(hint) or hint.startswith("data/"):
        return hint
    return f"data/playwright-profiles/{hint}"

# ---------- smart locator grammar ----------
# Accepts: css=..., xpath=..., text=..., role=button[name='Sign in'], id=#q, data-test=[data-test=q]
LOC_PREFIXES = ("css=", "xpath=", "text=", "role=", "id=", "data=", "aria=")

def _to_locator(page: Page, loc: str) -> Locator:
    s = loc.strip()
    if s.startswith("css="):
        return page.locator(s[4:])
    if s.startswith("xpath="):
        return page.locator(f"xpath={s[6:]}")
    if s.startswith("text="):
        return page.get_by_text(s[5:], exact=False)
    if s.startswith("id="):
        sel = s[3:]
        if not sel.startswith("#"):
            sel = f"#{sel}"
        return page.locator(sel)
    if s.startswith("data="):
        return page.locator(f"[data-test={s[5:]}], [data-testid={s[5:]}], [data-qa={s[5:]}]")
    if s.startswith("aria="):
        # aria=name or aria=role[name='..']
        val = s[5:]
        if val.startswith("role="):
            # role=button[name='Sign in']
            m = re.match(r"role=(\w+)\[name=['\"](.+?)['\"]\]", val)
            if m:
                role, name = m.group(1), m.group(2)
                return page.get_by_role(role=role, name=name)
        return page.get_by_role(name=val)
    if s.startswith("role="):
        # role=button[name='Accept all']
        m = re.match(r"role=(\w+)\[name=['\"](.+?)['\"]\]", s)
        if m:
            role, name = m.group(1), m.group(2)
            return page.get_by_role(role=role, name=name)
        return page.get_by_role(role=s.split("=",1)[1])
    # bare CSS or #id or .class or //xpath
    if s.startswith("//"):
        return page.locator(f"xpath={s}")
    return page.locator(s)

# ---------- cookie banner auto-dismiss ----------
COOKIE_SELECTORS = [
    "role=button[name='Accept all']",
    "role=button[name='I agree']",
    "role=button[name='Agree']",
    "button:has-text('Accept')",
    "button:has-text('I agree')",
    "[aria-label='Accept all']",
    "[data-testid='cookie-accept-all']",
]

async def _dismiss_cookies(page: Page, logs: List[str]) -> bool:
    try:
        for sel in COOKIE_SELECTORS:
            try:
                loc = _to_locator(page, sel) if any(sel.startswith(p) for p in LOC_PREFIXES) else page.locator(sel)
                if await loc.first.is_visible():
                    await loc.first.click(timeout=1500)
                    _log(logs, f"dismissed cookie banner via {sel}")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

# ---------- main executor ----------
async def browser_execute(
    actions: List[Dict[str, Any]],
    profile: str = "data/playwright-profiles/default",
    headless: bool = False,
    default_timeout_ms: int = 30000,
    screenshot_dir: str = "data/screens",
) -> Dict[str, Any]:
    """
    Generic browser executor. Supports ops:
    - goto {url, wait_until?}
    - wait_ms {ms}
    - wait_for {locator, state? visible|attached|detached, timeout_ms?}
    - click {locator, nth?, timeout_ms?}
    - type {locator, text, clear?, press_enter?, delay_ms?}
    - press {keys}  # e.g., "Control+L", "Enter"
    - eval  {js}
    - scroll {to: 'bottom'|'top'|locator, x?, y?}
    - screenshot {path?, full_page?, locator?}
    - ensure_url {includes?|matches?}
    - ensure_text {locator, includes?}
    - download {url? | click_locator?, filename?, dir?, allowed_ext?, allowed_domains?}
    """
    os.makedirs(screenshot_dir, exist_ok=True)
    logs: List[str] = []
    results: List[Dict[str, Any]] = []

    profile = _profile_path(profile)
    _, ctx = await _get_ctx(profile, headless=headless)
    page = await _get_page(ctx)
    page.set_default_timeout(default_timeout_ms)

    async def _step(op: str, params: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal page
        try:
            if op == "goto":
                url = params["url"]
                wu = params.get("wait_until", "domcontentloaded")
                await page.goto(url, wait_until=wu)
                return {"ok": True, "title": await page.title(), "url": page.url}

            if op == "wait_ms":
                await asyncio.sleep(max(0, params.get("ms", 500)) / 1000.0)
                return {"ok": True}

            if op == "wait_for":
                loc = _to_locator(page, params["locator"])
                state = params.get("state", "visible")
                to = params.get("timeout_ms", default_timeout_ms)
                await loc.wait_for(state=state, timeout=to)
                return {"ok": True}

            if op == "click":
                nth = params.get("nth")
                loc = _to_locator(page, params["locator"])
                target = loc.nth(nth) if (nth is not None) else loc.first
                await target.click(timeout=params.get("timeout_ms", default_timeout_ms))
                return {"ok": True}

            if op == "type":
                loc = _to_locator(page, params["locator"])
                if params.get("clear"):
                    await (loc.first).fill("")
                txt = params.get("text", "")
                await (loc.first).type(txt, delay=params.get("delay_ms", 20))
                if params.get("press_enter"):
                    await page.keyboard.press("Enter")
                return {"ok": True}

            if op == "press":
                keys = params["keys"]
                # support "Control+L", "Alt+F4", "Enter"
                await page.keyboard.press(keys)
                return {"ok": True}

            if op == "eval":
                js = params["js"]
                result = await page.evaluate(js)
                return {"ok": True, "result": result}

            if op == "scroll":
                to = params.get("to")
                if to in {"bottom", "top"}:
                    js = "window.scrollTo(0, document.body.scrollHeight);" if to == "bottom" else "window.scrollTo(0,0);"
                    await page.evaluate(js)
                    return {"ok": True}
                if "locator" in params:
                    loc = _to_locator(page, params["locator"]).first
                    await loc.scroll_into_view_if_needed()
                    return {"ok": True}
                if "x" in params or "y" in params:
                    x = int(params.get("x", 0)); y = int(params.get("y", 0))
                    await page.evaluate(f"window.scrollBy({x},{y});")
                    return {"ok": True}
                return {"ok": False, "error": "scroll_params_missing"}

            if op == "screenshot":
                path = params.get("path") or os.path.join(screenshot_dir, f"shot-{int(time.time())}.png")
                full = params.get("full_page", False)
                if params.get("locator"):
                    loc = _to_locator(page, params["locator"]).first
                    await loc.screenshot(path=path)
                else:
                    await page.screenshot(path=path, full_page=full)
                return {"ok": True, "path": path}

            if op == "ensure_url":
                inc = params.get("includes")
                match = params.get("matches")
                u = page.url
                if inc and inc not in u:
                    return {"ok": False, "error": f"url_missing_substring:{inc}", "url": u}
                if match and not re.search(match, u):
                    return {"ok": False, "error": f"url_not_matching:{match}", "url": u}
                return {"ok": True, "url": u}

            if op == "ensure_text":
                loc = _to_locator(page, params["locator"]).first
                txt = await loc.inner_text()
                inc = params.get("includes", "")
                if inc and inc not in (txt or ""):
                    return {"ok": False, "error": "text_not_found", "got": txt}
                return {"ok": True, "text": txt}

            if op == "download":
                ddir = params.get("dir", "data/downloads")
                os.makedirs(ddir, exist_ok=True)
                allowed_ext = tuple(params.get("allowed_ext", [".zip",".msi",".exe",".pdf",".csv",".xlsx",".txt"]))
                allowed_domains = params.get("allowed_domains")

                async def expect_dl():
                    async with page.expect_download(timeout=params.get("timeout_ms", 120000)) as dl_info:
                        if "url" in params and params["url"]:
                            from urllib.parse import urlparse
                            if allowed_domains:
                                host = (urlparse(params["url"]).hostname or "").lower()
                                if host and host not in [h.lower() for h in allowed_domains]:
                                    raise ValueError(f"domain_not_allowed:{host}")
                            await page.goto(params["url"])
                        else:
                            loc = _to_locator(page, params["click_locator"])
                            await loc.first.click()
                    return await dl_info.value

                dl: Download = await expect_dl()
                suggested = await dl.suggested_filename()
                fname = params.get("filename") or suggested
                if pathlib.Path(fname).suffix.lower() not in allowed_ext:
                    if params.get("filename") and pathlib.Path(suggested).suffix.lower() in allowed_ext:
                        fname = suggested
                    else:
                        raise ValueError(f"extension_not_allowed:{pathlib.Path(fname).suffix}")

                target = _safe_join(ddir, fname)
                await dl.save_as(target)
                failure = await dl.failure()
                if failure:
                    return {"ok": False, "error": f"download_failed:{failure}"}
                size = os.path.getsize(target)
                sha = ""
                try:
                    h = hashlib.sha256()
                    with open(target, "rb") as f:
                        for chunk in iter(lambda: f.read(1<<20), b""):
                            h.update(chunk)
                    sha = h.hexdigest()
                except Exception:
                    pass
                return {"ok": True, "path": target, "size_bytes": size, "sha256": sha}

            return {"ok": False, "error": f"unknown_op:{op}"}
        except Exception as e:
            return {"ok": False, "error": f"{op}_error:{e}"}

    # execute with light auto-heal
    for i, step in enumerate(actions, 1):
        op = step.get("op") or step.get("action")
        if not op:
            results.append({"ok": False, "error": "missing_op"})
            continue

        params = dict(step.get("params") or step.get("arguments") or {})
        # mask secrets in logs
        pretty = {k: (_mask(v) if k in {"text","password","pwd"} else v) for k, v in params.items()}
        _log(logs, f"{i}. {op} {json.dumps(pretty, ensure_ascii=False)}")

        # try once, then auto-dismiss cookies and retry once
        obs = await _step(op, params)
        if not obs.get("ok"):
            healed = await _dismiss_cookies(page, logs)
            if healed:
                obs = await _step(op, params)

        results.append(obs)

        # short-circuit on hard failures, keep going on soft
        if not obs.get("ok") and step.get("fail_fast", True):
            _log(logs, f"stopping at step {i} due to error: {obs.get('error')}")
            break

    return {"ok": True, "results": results, "logs": logs, "final_url": page.url}
