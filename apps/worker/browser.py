# apps/worker/browser.py
from __future__ import annotations
import os, asyncio, pathlib, hashlib
from typing import Tuple, Optional, Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Playwright, Page
from playwright.async_api import async_playwright, BrowserContext, Playwright, Page
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from playwright.async_api import Download
# keep one persistent context per profile on disk
_CTX: dict[str, Tuple[Playwright, BrowserContext]] = {}

async def _get_ctx(profile_dir: str = "data/playwright-profiles/default",
                   headless: bool = False) -> tuple[Playwright, BrowserContext]:
    os.makedirs(profile_dir, exist_ok=True)
    if profile_dir in _CTX:
        return _CTX[profile_dir]
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=headless,
        args=["--disable-dev-shm-usage", "--no-sandbox"],
        accept_downloads=True,  # <<< important
    )
    _CTX[profile_dir] = (pw, ctx)
    return pw, ctx


def _safe_join(base_dir: str, name: str) -> str:
    base = pathlib.Path(base_dir).resolve()
    target = (base / name).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("path_traversal_blocked")
    return str(target)

def _allowed_ext(filename: str, allow: tuple[str, ...]) -> bool:
    return pathlib.Path(filename).suffix.lower() in allow

async def browser_download(
    url: Optional[str] = None,
    click_selector: Optional[str] = None,
    profile: str = "data/playwright-profiles/default",
    download_dir: str = "data/downloads",
    filename: Optional[str] = None,
    timeout_ms: int = 120_000,
    headless: bool = False,
    allowed_ext: tuple[str, ...] = (".zip", ".msi", ".exe", ".pdf", ".csv", ".xlsx", ".txt"),
    allowed_domains: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Download a file either by visiting a direct URL or by clicking a selector that triggers a download.
    Saves file to `download_dir` (created if needed) and returns metadata.
    """
    os.makedirs(download_dir, exist_ok=True)
    _, ctx = await _get_ctx(profile, headless=headless)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    async def _expect() -> Download:
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            if url:
                # Optional domain guard
                if allowed_domains:
                    host = urlparse(url).hostname or ""
                    if host and host not in allowed_domains:
                        raise ValueError(f"domain_not_allowed: {host}")
                await page.goto(url)
            else:
                if not click_selector:
                    raise ValueError("provide url or click_selector")
                await page.click(click_selector)
        return await dl_info.value

    dl: Download = await _expect()

    # Suggested name and extension guard
    suggested = await dl.suggested_filename()
    final_name = filename or suggested
    if not _allowed_ext(final_name, allowed_ext):
        # try to infer extension from suggested name if custom name was provided without ext
        if filename and _allowed_ext(suggested, allowed_ext):
            final_name = suggested
        else:
            raise ValueError(f"extension_not_allowed: {pathlib.Path(final_name).suffix}")

    target_path = _safe_join(download_dir, final_name)

    # Save
    await dl.save_as(target_path)
    failure = await dl.failure()
    if failure:
        return {"ok": False, "error": f"download_failed: {failure}"}

    # Metadata
    size = os.path.getsize(target_path)
    sha256 = ""
    try:
        h = hashlib.sha256()
        with open(target_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        sha256 = h.hexdigest()
    except Exception:
        pass

    return {
        "ok": True,
        "path": target_path,
        "filename": os.path.basename(target_path),
        "size_bytes": size,
        "sha256": sha256,
        "page_url": page.url,
    }

async def _get_ctx(profile_dir: str = "data/playwright-profiles/default",
                   headless: bool = False) -> Tuple[Playwright, BrowserContext]:
    os.makedirs(profile_dir, exist_ok=True)
    if profile_dir in _CTX:
        return _CTX[profile_dir]
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=headless,
        args=["--disable-dev-shm-usage", "--no-sandbox"],
    )
    _CTX[profile_dir] = (pw, ctx)
    return pw, ctx

async def _get_page(ctx: BrowserContext) -> Page:
    if ctx.pages:
        return ctx.pages[0]
    return await ctx.new_page()

# ------------ Tools (async) ------------

async def browser_nav(url: str,
                      profile: str = "data/playwright-profiles/default",
                      wait_until: str = "domcontentloaded",
                      headless: bool = False,
                      timeout_ms: int = 30000) -> Dict[str, Any]:
    _, ctx = await _get_ctx(profile, headless=headless)
    page = await _get_page(ctx)
    await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
    title = await page.title()
    return {"ok": True, "url": page.url, "title": title}

async def browser_type(selector: str,
                       text: str,
                       profile: str = "data/playwright-profiles/default",
                       clear: bool = False,
                       press_enter: bool = False,
                       type_delay_ms: int = 20) -> Dict[str, Any]:
    _, ctx = await _get_ctx(profile)
    page = await _get_page(ctx)
    el = await page.wait_for_selector(selector, timeout=15000)
    if clear:
        await el.fill("")
    await el.type(text, delay=type_delay_ms)
    if press_enter:
        await page.keyboard.press("Enter")
    return {"ok": True}

async def browser_click(selector: str,
                        profile: str = "data/playwright-profiles/default",
                        timeout_ms: int = 15000) -> Dict[str, Any]:
    _, ctx = await _get_ctx(profile)
    page = await _get_page(ctx)
    await page.click(selector, timeout=timeout_ms)
    return {"ok": True}

async def browser_wait_ms(ms: int = 500) -> Dict[str, Any]:
    await asyncio.sleep(max(ms, 0) / 1000.0)
    return {"ok": True}

async def browser_eval(js: str,
                       profile: str = "data/playwright-profiles/default") -> Dict[str, Any]:
    _, ctx = await _get_ctx(profile)
    page = await _get_page(ctx)
    result = await page.evaluate(js)
    return {"ok": True, "result": result}
