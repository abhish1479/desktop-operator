import re
import os, time, json
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

SYSTEM_PROMPT = """
You are a Desktop Operator that plans and executes tasks using tools.
Always prefer robust, generic flows that will work across many sites/apps.
Assume Windows. Persist browser sessions using a profile when needed.

## Tool Catalog (canonical names)
- fs_write(path, content)
- fs_move(src, dst)
- fs_listdir(path)

- terminal_run(cmd, shell?="powershell", timeout_sec?=120)

- vscode_open(path, line?)
- vscode_save_all()
- vscode_get_diagnostics()

- app_launch(name)   # prefer this over terminal for desktop apps

- ui_focus(title_re)                           # focus a desktop window by title regex
- ui_menu_select(path)                         # e.g., "File->Open"
- ui_click(name, control_type)                 # e.g., ("OK", "Button")
- ui_type(text)

### Browser (async Playwright)
Prefer the generic one-call executor for multi-step automation:
- browser_execute(actions, profile?="default", headless?=False, default_timeout_ms?=30000)
  Each action = { op, params }. Supported ops:
  - goto {url, wait_until?}
  - wait_ms {ms}
  - wait_for {locator, state?=visible, timeout_ms?}
  - click {locator, nth?, timeout_ms?}
  - type {locator, text, clear?=false, press_enter?=false, delay_ms?=20}
  - press {keys}
  - eval {js}
  - scroll {to?='top'|'bottom'|, locator?|, x?|, y?}
  - screenshot {path?, full_page?=false, locator?}
  - ensure_url {includes?|matches?}
  - ensure_text {locator, includes}
  - download {url? | click_locator?, filename?, dir?="data/downloads",
             allowed_ext?=[".zip",".msi",".exe",".pdf",".csv",".xlsx",".txt"],
             allowed_domains?=[...]}

Granular browser tools:
- browser_nav(url, profile?="default", wait_until?="domcontentloaded")
- browser_type(selector, text, profile?="default", clear?=false, press_enter?=false, type_delay_ms?=20)
- browser_click(selector, profile?="default", timeout_ms?=15000)
- browser_wait_ms(ms)
- browser_eval(js, profile?="default")
- browser_download(url? | click_selector?, profile?="default", download_dir?="data/downloads", filename?, timeout_ms?=120000)

## Rules & Safety
- Secrets: If the user includes passwords/OTPs, **use them** but never echo or log them. In any text you produce, mask with "***".
- Approvals: For destructive or high-impact actions (sending emails/messages, purchasing, installing, deleting/moving many files), show a short plan and ask for explicit approval unless the user said “dry run off / go ahead”.
- Use direct file APIs (fs.*) instead of typing into GUI file pickers.
- Prefer app.launch over terminal.run for desktop apps; for installs use terminal.run with **minimal, vetted** commands (e.g., winget) and show a plan first.
- In browsers, avoid brittle coordinates. Use robust locators (role/name/text). If a cookie banner blocks actions, try an “Accept all” button by role/text; otherwise continue.
- Long logs: summarize in 2–4 lines; attach key paths/URLs instead of raw dumps.
- 2FA/CAPTCHAs: pause and ask the user for the code or how to proceed.
- Stop as soon as the stated goal is achieved; include stop=true in your observation.

## Planning Pattern
1) Confirm assumptions in one sentence if needed; if secrets are required, request them.
2) Propose a **brief** plan (bullets). If risky/destructive, ask for approval.
3) Execute:
   - Prefer **browser_execute** with a compact list of actions for web automation (include profile if login/state is needed).
   - Otherwise call granular tools or UI/app tools as appropriate.
4) Verify outcome (ensure_url / ensure_text / fs_listdir / terminal_run --version, etc.).
5) Return a concise result with key artifacts (paths, URLs, screenshots). If done, set stop=true.

## Output: Tool Calls
When you need to act, emit a single JSON tool call like:
{"name": "<tool_name>", "arguments": {...}}
For browser_execute:
{"name":"browser_execute","arguments":{
  "profile":"default",
  "actions":[
    {"op":"goto","params":{"url":"https://www.youtube.com/"}},
    {"op":"type","params":{"locator":"input#search","text":"Kesariya Arijit Singh official","press_enter":true}},
    {"op":"wait_ms","params":{"ms":1200}},
    {"op":"click","params":{"locator":"ytd-video-renderer a#thumbnail"}},
    {"op":"wait_ms","params":{"ms":1200}},
    {"op":"eval","params":{"js":"document.querySelector('video')?.play?.();"}},
    {"op":"eval","params":{"js":"const v=document.querySelector('video'); if(v){ v.volume=0.3; }"}},
    {"op":"screenshot","params":{"path":"data/screens/yt-now.png"}}
  ]
}}

## Generic Patterns (examples to adapt)
- Login + 2FA (web): browser.execute with goto → type email → type password (masked) → press Enter → wait_for dashboard → screenshot.
- Read and reply email (approval): search sender → open latest → eval to extract body (or screenshot) → draft reply text (ask approval) → click Reply → type → send → screenshot thread.
- Download: goto product page → click download → browser.download{click_locator:"..."} with allowed_domains and filename.
- Form/CRUD: goto → wait_for form → type fields → click submit → ensure_text{...}.
- Local project setup: fs.write → terminal.run (pip/uvicorn/pytest) → vscode.open → vscode.get_diagnostics.

Be decisive, resilient, and generic. Avoid site-specific hacks unless absolutely necessary.
"""

# Keep your SYSTEM_PROMPT exactly as you already have it above.

class LLM:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.start_time = time.time()
        self.last_raw: Dict[str, Any] | None = None
        self._last_tool_call_id: str | None = None
        # Cost tracking
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.total_cost_inr: float = 0.0

    def bootstrap(self, goal: str, dry_run: bool, budget_rupees: Optional[int]):
        # Reset per-run state to avoid leaking tool_call IDs across runs
        self._last_tool_call_id = None
        self.last_raw = None
        sys = SYSTEM_PROMPT + f"\nUser dry_run={dry_run}, budget_rupees={budget_rupees}.\n"
        return [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"Goal: {goal}"},
        ]

    def _tool_specs(self) -> List[Dict[str, Any]]:
        def fn(name: str, params: Dict[str, Any]) -> Dict[str, Any]:
            return {"type": "function", "function": {"name": name, "parameters": params}}

        def req(*keys: str) -> Dict[str, Any]:
            return {
                "type": "object",
                "properties": {k: {"type": "string"} for k in keys},
                "required": list(keys),
                "additionalProperties": True,
            }

        any_obj: Dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": True}

        return [
            fn("fs_read",     req("path")),
            fn("fs_write",    {"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},
                               "required":["path","content"], "additionalProperties":True}),
            fn("fs_move",     req("src","dst")),
            fn("fs_copy",     req("src","dst")),
            fn("fs_delete",   req("path")),
            fn("fs_listdir",  req("path")),

            fn("pkg_install",   any_obj),
            fn("pkg_uninstall", any_obj),
            fn("pkg_ensure",    any_obj),

            fn("terminal_run", {
                "type":"object",
                "properties":{"cmd":{"type":"string"},"shell":{"type":"string"},"timeout_sec":{"type":"integer"}},
                "required":["cmd"], "additionalProperties": True
            }),

            fn("vscode_open",            req("path")),
            fn("vscode_save_all",        any_obj),
            fn("vscode_get_diagnostics", any_obj),
            fn("vscode_install_extension", {
                "type":"object","properties":{"ext_id":{"type":"string"},"force":{"type":"boolean"}},
                "required":["ext_id"], "additionalProperties": True
            }),

            fn("app_launch",     req("name")),
            fn("ui_focus",       req("title_re")),
            fn("ui_menu_select", req("path")),
            fn("ui_click", {
                "type":"object","properties":{"name":{"type":"string"},"control_type":{"type":"string"}},
                "required":["name"], "additionalProperties": True
            }),
            fn("ui_type",        req("text")),
            fn("ui_wait",        {"type":"object","properties":{"ms":{"type":"integer"}},"required":["ms"],"additionalProperties":True}),
            fn("ui_shortcut",    req("keys")),

            fn("http_request", any_obj),
            fn("data_csv_read",  any_obj),
            fn("data_csv_write", any_obj),
            fn("data_json_read", any_obj),
            fn("data_json_write", any_obj),

            fn("browser_nav",      req("url")),
            fn("browser_click",    {"type":"object","properties":{"selector":{"type":"string"},"by":{"type":"string"},"name":{"type":"string"}},
                                    "required":["selector"], "additionalProperties":True}),
            fn("browser_type",     {"type":"object","properties":{"selector":{"type":"string"},"text":{"type":"string"},"press_enter":{"type":"boolean"}},
                                    "required":["selector","text"], "additionalProperties":True}),
            fn("browser_wait_ms",  {"type":"object","properties":{"ms":{"type":"integer"}},"required":["ms"],"additionalProperties":True}),
            fn("browser_eval",     {"type":"object","properties":{"js":{"type":"string"}},"required":["js"],"additionalProperties":True}),
            fn("browser_download", any_obj),
            fn("browser_execute",  {
                "type":"object",
                "properties":{
                    "actions":{"type":"array","items":{"type":"object","additionalProperties":True}},
                    "profile":{"type":"string"},
                    "headless":{"type":"boolean"},
                    "default_timeout_ms":{"type":"integer"}
                },
                "required":["actions"], "additionalProperties": True
            }),

            # WhatsApp Desktop chat tools (permissive schema to allow future args)
            fn("whatsapp_desktop_chat", any_obj),
            fn("whatsapp_send",         any_obj),
        ]

    # -------------- Tool-call Parsing Helpers --------------
    def _extract_tool_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Rescue path: if the model printed a tool call as JSON in the assistant text.
        We try to find a JSON object with "name" and "arguments".
        """
        if not text:
            return None
        # Strip fences ```json ... ```
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
        if m:
            try:
                obj = json.loads(m.group(1))
                if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                    return {"name": obj["name"], "arguments": obj.get("arguments") or {}}
            except Exception:
                pass
        # Fallback: first { ... } blob
        m = re.search(r"(\{.*\})", text, flags=re.S)
        if m:
            try:
                obj = json.loads(m.group(1))
                if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                    return {"name": obj["name"], "arguments": obj.get("arguments") or {}}
            except Exception:
                pass
        return None

    # ----------------- Next Tool Call -----------------
    def next_tool_call(self, messages: List[Dict[str,Any]]) -> Optional[Dict[str,Any]]:
        # ---- Stub mode (no API key) ----
        if not self.api_key:
            goal = [m for m in messages if m["role"] == "user"][-1]["content"].lower()
            call: Dict[str, Any]
            if ("youtube" in goal) or ("play " in goal):
                call = {
                    "name": "browser.execute",
                    "arguments": {
                        "actions": [
                            {"op":"goto","params":{"url":"https://www.youtube.com/"}},
                            {"op":"wait_for","params":{"locator":"role=combobox[name='Search']","timeout_ms":10000}},
                            {"op":"type","params":{"locator":"role=combobox[name='Search']","text":"saiyaraa","press_enter":True}},
                            {"op":"wait_for","params":{"locator":"ytd-video-renderer a#thumbnail","timeout_ms":15000}},
                            {"op":"click","params":{"locator":"ytd-video-renderer a#thumbnail","nth":0}},
                            {"op":"wait_ms","params":{"ms":1200}},
                            {"op":"eval","params":{"js":"document.querySelector('video')?.play?.();"}}
                        ]
                    }
                }
            elif ("flutter" in goal) or ("create project" in goal):
                call = {"name":"terminal.run","arguments":{"cmd":"flutter --version","shell":"powershell","timeout_sec":180}}
            else:
                call = {"name":"fs.listdir","arguments":{"path":"."}}
            # record for streaming debug
            self.last_raw = {"path": "stub", "reason": "no_api_key", "emitted_call": call, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "cost_usd": 0.0, "cost_inr": 0.0}
            return call

        # ---- Real API call ----
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self._tool_specs(),
                tool_choice="auto",
                temperature=0.2,
            )

            # Token usage and cost estimation
            usage = getattr(resp, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
            total_tokens = getattr(usage, "total_tokens", 0) if usage else (prompt_tokens + completion_tokens)
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens
            self.total_tokens += total_tokens
            # Cost calculation (if env prices provided)
            try:
                in_price = float(os.getenv("OPENAI_PRICE_INPUT_PER_1K", "0"))
                out_price = float(os.getenv("OPENAI_PRICE_OUTPUT_PER_1K", "0"))
                usd_to_inr = float(os.getenv("USD_TO_INR", "83.0"))
            except Exception:
                in_price = out_price = 0.0
                usd_to_inr = 83.0
            cost_usd = (prompt_tokens / 1000.0) * in_price + (completion_tokens / 1000.0) * out_price
            cost_inr = cost_usd * usd_to_inr
            self.total_cost_usd += cost_usd
            self.total_cost_inr += cost_inr

            choice = resp.choices[0]
            msg = getattr(choice, "message", None)

            # capture everything for live debug
            tool_calls = []
            if msg and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": tc.type,
                        "name": getattr(tc.function, "name", None) if getattr(tc, "function", None) else None,
                        "arguments": getattr(tc.function, "arguments", None) if getattr(tc, "function", None) else None,
                    })

            self.last_raw = {
                "finish_reason": choice.finish_reason,
                "message_content": getattr(msg, "content", None),
                "tool_calls": tool_calls,
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost_usd": round(cost_usd, 6),
                    "cost_inr": round(cost_inr, 2),
                    "total_cost_usd": round(self.total_cost_usd, 6),
                    "total_cost_inr": round(self.total_cost_inr, 2),
                },
            }

            # Prefer tool_calls if present
            if tool_calls:
                first = tool_calls[0]
                self._last_tool_call_id = first.get("id")
                args = {}
                try:
                    args = json.loads(first.get("arguments") or "{}")
                except Exception:
                    args = {}
                return {"name": first.get("name"), "arguments": args}

            # Try to rescue a tool call from assistant text
            assistant_text = getattr(msg, "content", None)
            rescued = self._extract_tool_from_text(assistant_text or "")
            if rescued:
                return rescued

            # No tool call; append assistant text so the planner can iterate
            messages.append({"role": "assistant", "content": assistant_text or ""})
            return None

        except Exception as e:
            # Surface the exception to your stream
            self.last_raw = {"error": str(e)}
            messages.append({"role": "assistant", "content": f"LLM error: {e}"})
            return None

    # ----------------- Observe -----------------
    def observe(self, messages, tool_name, args, obs):
        payload = {"tool": tool_name, "args": args, "observation": obs}
        # Only send a tool message when responding to a prior tool_call
        if self._last_tool_call_id:
            msg = {"role": "tool", "content": json.dumps(payload), "name": tool_name, "tool_call_id": self._last_tool_call_id}
            self._last_tool_call_id = None
            messages.append(msg)
        else:
            # No tool_call to respond to; provide a short assistant summary instead
            try:
                snippet = json.dumps(obs, ensure_ascii=False)
            except Exception:
                snippet = str(obs)
            messages.append({"role": "assistant", "content": f"Observation: {snippet[:2000]}"})
        return messages
