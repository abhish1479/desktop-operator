import os, time, json
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

SYSTEM_PROMPT = """
You are a Desktop Operator that plans and executes tasks using tools.
Always prefer robust, generic flows that will work across many sites/apps.
Assume Windows. Persist browser sessions using a profile when needed.

## Tool Catalog (canonical names)
- fs.write(path, content)
- fs.move(src, dst)
- fs.listdir(path)

- terminal.run(cmd, shell?="powershell", timeout_sec?=120)

- vscode.open(path, line?)
- vscode.save_all()
- vscode.get_diagnostics()

- app.launch(name)   # prefer this over terminal for desktop apps

- ui.focus(title_re)                           # focus a desktop window by title regex
- ui.menu_select(path)                         # e.g., "File->Open"
- ui.click(name, control_type)                 # e.g., ("OK", "Button")
- ui.type(text)

### Browser (async Playwright)
Prefer the generic one-call executor for multi-step automation:
- browser.execute(actions, profile?="default", headless?=False, default_timeout_ms?=30000)
  Each action = { op, params }. Supported ops:
  - goto {url, wait_until?}
  - wait_ms {ms}
  - wait_for {locator, state?=visible, timeout_ms?}
  - click {locator, nth?, timeout_ms?}
  - type {locator, text, clear?=false, press_enter?=false, delay_ms?=20}
  - press {keys}                         # e.g., "Enter", "Control+L"
  - eval {js}                            # run JS and return value
  - scroll {to?='top'|'bottom'|, locator?|, x?|, y?}
  - screenshot {path?, full_page?=false, locator?}
  - ensure_url {includes?|matches?}      # soft assertions
  - ensure_text {locator, includes}
  - download {url? | click_locator?, filename?, dir?="data/downloads",
             allowed_ext?=[".zip",".msi",".exe",".pdf",".csv",".xlsx",".txt"],
             allowed_domains?=[...]}
Smart locators allowed: css=..., xpath=..., text=..., role=button[name='...'], id=..., data=..., aria=...
For persistent login, include profile="default" (or another profile). Avoid site-specific selectors if a role/text works.

Granular browser tools (use when a single action is enough):
- browser.nav(url, profile?="default", wait_until?="domcontentloaded")
- browser.type(selector, text, profile?="default", clear?=false, press_enter?=false, type_delay_ms?=20)
- browser.click(selector, profile?="default", timeout_ms?=15000)
- browser.wait_ms(ms)
- browser.eval(js, profile?="default")
- browser.download(url? | click_selector?, profile?="default", download_dir?="data/downloads", filename?, timeout_ms?=120000)

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
   - Prefer **browser.execute** with a compact list of actions for web automation (include profile if login/state is needed).
   - Otherwise call granular tools or UI/app tools as appropriate.
4) Verify outcome (ensure_url / ensure_text / fs.listdir / terminal.run --version, etc.).
5) Return a concise result with key artifacts (paths, URLs, screenshots). If done, set stop=true.

## Output: Tool Calls
When you need to act, emit a single JSON tool call like:
{"name": "<tool_name>", "arguments": {...}}
For browser.execute:
{"name":"browser.execute","arguments":{
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

class LLM:
    """
    - Exposes the same API you already use.
    - Tools list now matches your TOOL_REGISTRY keys (dot names) AND includes browser.execute.
    - Robust tool-call detection (checks message.tool_calls).
    - Emits detailed self.last_raw for your TracedLLM to show in /tasks/run_stream.
    - Keeps an internal tool_call_id so observe() threads properly.
    """
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.start_time = time.time()
        self.last_raw: Dict[str, Any] | None = None
        self._last_tool_call_id: str | None = None

    def bootstrap(self, goal: str, dry_run: bool, budget_rupees: Optional[int]):
        sys = SYSTEM_PROMPT + f"\nUser dry_run={dry_run}, budget_rupees={budget_rupees}.\n"
        return [
            {"role": "system", "content": sys},
            {"role": "user", "content": f"Goal: {goal}"}
        ]

    def _tool_specs(self) -> List[Dict[str, Any]]:
        # Match your registry keys. Include browser.execute and canonical dot names.
        # helper to build a tool schema
        def fn(name: str, params: Dict[str, Any]) -> Dict[str, Any]:
            return {"type": "function", "function": {"name": name, "parameters": params}}

        # require a set of string fields (kept permissive)
        def req(*keys: str) -> Dict[str, Any]:
            return {
                "type": "object",
                "properties": {k: {"type": "string"} for k in keys},
                "required": list(keys),
                "additionalProperties": True,
            }

        # fully permissive object (for flexible tools)
        any_obj: Dict[str, Any] = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        
        return [
        # Filesystem (align with registry dot names)
            fn("fs.read",     req("path")),
            fn("fs.write",    {"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}),
            fn("fs.move",     req("src","dst")),
            fn("fs.copy",     req("src","dst")),
            fn("fs.delete",   req("path")),
            fn("fs.listdir",  req("path")),

            # Packages (used for Git, JDK, Flutter, Android Studio via winget/choco)
            fn("pkg.install",   any_obj),
            fn("pkg.uninstall", any_obj),
            fn("pkg.ensure",    any_obj),

            # Terminal
            fn("terminal.run", {"type":"object","properties":{"cmd":{"type":"string"},"shell":{"type":"string"},"timeout_sec":{"type":"integer"}},"required":["cmd"],"additionalProperties":True}),

            # VS Code (your registry exposes these names)
            fn("vscode_open",            req("path")),
            fn("vscode_save_all",        any_obj),
            fn("vscode_get_diagnostics", any_obj),
            fn("vscode.install_extension", {"type":"object","properties":{"ext_id":{"type":"string"},"force":{"type":"boolean"}},"required":["ext_id"],"additionalProperties":True}),

            # UI / App launch
            fn("app_launch",  req("name")),
            fn("ui.focus",    req("title_re")),
            fn("ui.menu_select", req("path")),
            fn("ui.click",    {"type":"object","properties":{"name":{"type":"string"},"control_type":{"type":"string"}},"required":["name"],"additionalProperties":True}),
            fn("ui.type",     req("text")),
            fn("ui.wait",     {"type":"object","properties":{"ms":{"type":"integer"}},"required":["ms"]}),
            fn("ui.shortcut", req("keys")),

            # HTTP / data (optional)
            fn("http.request", any_obj),
            fn("data.csv.read",  any_obj),
            fn("data.csv.write", any_obj),
            fn("data.json.read", any_obj),
            fn("data.json.write", any_obj),

            # Browser granular + executor
            fn("browser.nav",      req("url")),
            fn("browser.click",    {"type":"object","properties":{"selector":{"type":"string"},"by":{"type":"string"},"name":{"type":"string"}},"required":["selector"],"additionalProperties":True}),
            fn("browser.type",     {"type":"object","properties":{"selector":{"type":"string"},"text":{"type":"string"},"press_enter":{"type":"boolean"}},"required":["selector","text"],"additionalProperties":True}),
            fn("browser.wait_ms",  {"type":"object","properties":{"ms":{"type":"integer"}},"required":["ms"]}),
            fn("browser.eval",     {"type":"object","properties":{"js":{"type":"string"}},"required":["js"]}),
            fn("browser.download", any_obj),
            fn("browser.execute",  {
                "type":"object",
                "properties":{
                    "actions":{"type":"array","items":{"type":"object","additionalProperties":True}},
                    "profile":{"type":"string"},
                    "headless":{"type":"boolean"},
                    "default_timeout_ms":{"type":"integer"}
                },
                "required":["actions"], "additionalProperties":True
            }),
        ]

    def next_tool_call(self, messages: List[Dict[str,Any]]) -> Optional[Dict[str,Any]]:
        # If no API key, provide a minimal heuristic to unblock local tests
        if not self.api_key:
            last_user = [m for m in messages if m["role"] == "user"][-1]["content"].lower()
            if "youtube" in last_user or "play" in last_user:
                return {
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
            # fall back to a harmless listing
            return {"name":"fs.listdir", "arguments":{"path":"."}}

        # Real call via OpenAI
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

            choice = resp.choices[0]
            # capture everything for debugging
            self.last_raw = {
                "finish_reason": choice.finish_reason,
                "message": {
                    "content": getattr(choice.message, "content", None),
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "name": tc.function.name if getattr(tc, "function", None) else None,
                            "arguments": tc.function.arguments if getattr(tc, "function", None) else None,
                        }
                        for tc in (choice.message.tool_calls or [])
                    ],
                },
            }

            # Robust detection: if tool_calls exist, parse the first one
            tcs = choice.message.tool_calls or []
            if tcs:
                first = tcs[0]
                self._last_tool_call_id = first.id
                args = {}
                try:
                    args = json.loads(first.function.arguments or "{}")
                except Exception:
                    # leave args empty; the runner/validation will guard
                    args = {}
                return {"name": first.function.name, "arguments": args}

            # No tool call; keep the assistant content so the planner can continue if needed
            messages.append({"role": "assistant", "content": choice.message.content or ""})
            return None

        except Exception as e:
            # also expose the error in raw for your stream
            self.last_raw = {"error": str(e)}
            messages.append({"role": "assistant", "content": f"LLM error: {e}"})
            return None

    def observe(self, messages, tool_name, args, obs):
        # Thread tool output with tool_call_id when available (improves follow-ups)
        payload = {"tool": tool_name, "args": args, "observation": obs}
        msg = {"role": "tool", "content": json.dumps(payload), "name": tool_name}
        if self._last_tool_call_id:
            msg["tool_call_id"] = self._last_tool_call_id
            self._last_tool_call_id = None
        messages.append(msg)
        return messages

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.start_time = time.time()

    def bootstrap(self, goal: str, dry_run: bool, budget_rupees: Optional[int]):
        sys = SYSTEM_PROMPT + f"\nUser dry_run={dry_run}, budget_rupees={budget_rupees}.\n"
        return [
            {"role":"system","content": sys},
            {"role":"user","content": f"Goal: {goal}"}
        ]

    def next_tool_call(self, messages: List[Dict[str,Any]]) -> Optional[Dict[str,Any]]:
        # If no API key, simple stub planner
        if not self.api_key:
            last_user = [m for m in messages if m["role"]=="user"][-1]["content"].lower()
            if "organize" in last_user and "download" in last_user:
                return {"name":"fs_listdir", "arguments":{"path":"C:/Users/you/Downloads"}}
            return None

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            tools = [
                {"type": "function", "function": {"name": "fs_write", "parameters": {"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
                {"type": "function", "function": {"name": "fs_move", "parameters": {"type":"object","properties":{"src":{"type":"string"},"dst":{"type":"string"}},"required":["src","dst"]}}},
                {"type": "function", "function": {"name": "fs_listdir", "parameters": {"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
                {"type": "function", "function": {"name": "terminal_run", "parameters": {"type":"object","properties":{"cmd":{"type":"string"},"shell":{"type":"string"},"timeout_sec":{"type":"integer"}},"required":["cmd"]}}},
                {"type": "function", "function": {"name": "vscode_open", "parameters": {"type":"object","properties":{"path":{"type":"string"},"line":{"type":"integer"}}}}},
                {"type": "function", "function": {"name": "vscode_save_all", "parameters": {"type":"object","properties":{}}}},
                {"type": "function", "function": {"name": "vscode_get_diagnostics", "parameters": {"type":"object","properties":{}}}},
                {"type": "function", "function": {"name": "browser_nav", "parameters": {"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}}},
                {"type": "function", "function": {"name": "browser_click", "parameters": {"type":"object","properties":{"selector":{"type":"string"},"by":{"type":"string"},"name":{"type":"string"}},"required":["selector"]}}},
                {"type": "function", "function": {"name": "browser_type", "parameters": {"type":"object","properties":{"selector":{"type":"string"},"text":{"type":"string"},"press_enter":{"type":"boolean"}},"required":["selector","text"]}}},
                {"type": "function", "function": {"name": "browser_download", "parameters": {"type":"object","properties":{"selector":{"type":"string"},"to_dir":{"type":"string"}},"required":["selector","to_dir"]}}},
            ]

            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
            choice = resp.choices[0]
            if choice.finish_reason == "tool_calls":
                call = choice.message.tool_calls[0]
                return {"name": call.function.name, "arguments": json.loads(call.function.arguments or "{}")}
            else:
                messages.append({"role":"assistant","content": choice.message.content or ""})
                return None
        except Exception as e:
            messages.append({"role":"assistant","content": f"LLM error: {e}"})
            return None

    def observe(self, messages, tool_name, args, obs):
        payload = {"tool": tool_name, "args": args, "observation": obs}
        messages.append({"role":"tool","content": json.dumps(payload), "name": tool_name})
        return messages
