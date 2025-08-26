import os, time, json
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

SYSTEM_PROMPT = """You are a desktop Operator with tools:
- fs_write(path, content)
- fs_move(src, dst)
- fs_listdir(path)
- terminal_run(cmd, shell?='powershell', timeout_sec?=120)
- vscode_open(path, line?)
- vscode_save_all()
- vscode_get_diagnostics()
- browser_nav(url)
- browser_click(selector, by?='css', name?)
- browser_type(selector, text, press_enter?=false)
- browser_download(selector, to_dir)

Rules:
- Prefer direct filesystem & APIs over UI typing.
- Use terminal for installs, with safe, minimal commands.
- Summarize long logs before sending again.
- Stop when the goal is reached; set stop=true in the observation.
"""

class LLM:
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
