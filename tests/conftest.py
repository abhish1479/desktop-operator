from __future__ import annotations
import os, re, json, time
import pytest
from fastapi.testclient import TestClient

# Import your FastAPI app + the registry/policy it uses
from apps.orchestrator.main import app, get_llm
from apps.orchestrator.tools.registry import TOOL_REGISTRY
from apps.orchestrator.policy import policy
# tests/conftest.py
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class DummyLLM:
    """
    Minimal LLM shim:
      - bootstrap(goal, dry_run, budget) stores goal
      - next_tool_call(messages) returns the next planned tool call
      - observe(...) appends and allows the loop to continue
    It builds a plan from the *natural-language* goal using regex heuristics.
    """
    def __init__(self):
        self.goal = ""
        self.plan = []
        self.messages = []

    def bootstrap(self, goal: str, dry_run: bool, budget_rupees):
        self.goal = goal
        self.plan = self._build_plan_from_goal(goal)
        self.messages = [{"role":"system","content":"dummy"}]
        return self.messages

    def next_tool_call(self, messages):
        if not self.plan:
            return None
        return self.plan.pop(0)

    def observe(self, messages, tool_name, args, obs):
        # Simply append observation; no additional planning for tests
        self.messages.append({"role":"tool","name":tool_name,"args":args,"obs":obs})
        return self.messages

    # ----------------- planning helpers -----------------

    def _build_plan_from_goal(self, goal: str):
        g = goal.lower().strip()

        # 1) Filesystem “create & move & list”
        if re.search(r"\bcreate\b.*\bfile\b", g):
            return [
                {"name": "fs.write", "arguments": {"path":"data/test_sandbox/notes/hello.txt","content":"hello world"}},
                {"name": "fs.move",  "arguments": {"src":"data/test_sandbox/notes/hello.txt","dst":"data/test_sandbox/hello-moved.txt"}},
                {"name": "fs.listdir","arguments": {"path":"data/test_sandbox"}},
            ]

        # 2) Terminal echo (safe)
        if re.search(r"\bterminal\b.*\becho\b", g):
            return [
                {"name": "terminal.run", "arguments": {"cmd":"echo hello-from-terminal","shell":"powershell","timeout_sec":30}}
            ]

        # 3) HTTP GET
        if re.search(r"\bhttp\b.*\bget\b", g):
            return [
                {"name": "http.request", "arguments": {"method":"GET","url":"https://example.com"}}
            ]

        # 4) CSV write + read
        if re.search(r"\bcsv\b.*\bwrite\b", g) or re.search(r"\bwrite\b.*\bcsv\b", g):
            return [
                {"name":"data.csv.write","arguments":{
                    "path":"data/test_sandbox/out/data.csv",
                    "rows":[{"id":"1","item":"alpha"},{"id":"2","item":"beta"}],
                    "fieldnames":["id","item"]
                }},
                {"name":"data.csv.read","arguments":{"path":"data/test_sandbox/out/data.csv"}},
            ]

        # 5) JSON read/write (accept 'write json' or 'json write')
        if re.search(r"\bjson\b.*\bwrite\b", g) or re.search(r"\bwrite\b.*\bjson\b", g):
            return [
                {"name":"data.json.write","arguments":{
                    "path":"data/test_sandbox/out/info.json","data":{"ok":True,"ts":int(time.time())}
                }},
                {"name":"data.json.read","arguments":{"path":"data/test_sandbox/out/info.json"}},
            ]


        # 6) Package install (dry run)
        if re.search(r"\binstall\b.*\bgit\b", g):
            return [
                {"name":"pkg.install","arguments":{"id":"Git.Git","manager":"winget","silent":True,"dry_run":True}}
            ]

        # 7) VS Code open (just smoke)
        if re.search(r"\bopen\b.*\bvs\s*code\b", g):
            return [
                {"name":"vscode.open","arguments":{"path":"data/test_sandbox/README.md"}}
            ]

        # 8) Browser generic (only if enabled)
        # inside DummyLLM._build_plan_from_goal(self, goal)
        if "youtube" in g or ("play" in g and ("song" in g or "video" in g)):
            return [
                {"name":"browser.execute","arguments":{
                    "profile":"default",
                    "actions":[
                        {"op":"goto","params":{"url":"https://www.youtube.com/"}},
                        # Try to clear consent overlays (non-fatal)
                        {"op":"click","params":{"locator":"role=button[name='I agree']","timeout_ms":1500},"fail_fast":False},
                        {"op":"click","params":{"locator":"button:has-text('Accept all')","timeout_ms":1500},"fail_fast":False},

                        # Robust search: focus by role, then keyboard "/" to ensure caret
                        {"op":"wait_for","params":{"locator":"role=combobox[name='Search']","timeout_ms":10000}},
                        {"op":"click","params":{"locator":"role=combobox[name='Search']"}},
                        {"op":"press","params":{"keys":"/"}},
                        {"op":"type","params":{"locator":"role=combobox[name='Search']","text":"saiyaara kishore kumar 1980","press_enter":True}},
                        {"op":"wait_for","params":{"locator":"ytd-video-renderer a#thumbnail","timeout_ms":15000}},
                        {"op":"click","params":{"locator":"ytd-video-renderer a#thumbnail","nth":0}},
                        {"op":"wait_ms","params":{"ms":1500}},

                        # Start playback & set volume
                        {"op":"eval","params":{"js":"document.querySelector('video')?.play?.(); const v=document.querySelector('video'); if(v){ v.volume=0.25; } return !!v;"}},
                        {"op":"screenshot","params":{"path":"data/screens/yt-now.png"}}
                    ]
                }}
            ]


        # 9) Unknown tool to test error path
        if "unknown tool" in g:
            return [{"name": "does.not.exist", "arguments": {}}]

        # 10) Blocked tool test (terminal.run will be blocked by options in test)
        if "blocked terminal" in g:
            return [{"name": "terminal.run", "arguments":{"cmd":"echo should-be-blocked"}}]

        # 11) Timeout test (long sleep; policy patched in test to short timeout)
        if "timeout test" in g:
            return [{"name":"terminal.run","arguments":{"cmd":"Start-Sleep -Seconds 5","shell":"powershell"}}]

        # Default: harmless fs.listdir
        return [{"name":"fs.listdir","arguments":{"path":"."}}]


@pytest.fixture(autouse=True)
def sandbox_dirs(tmp_path, monkeypatch):
    os.makedirs("data/test_sandbox/notes", exist_ok=True)
    os.makedirs("data/test_sandbox/out", exist_ok=True)
    yield

@pytest.fixture()
def dummy_llm():
    return DummyLLM()

@pytest.fixture()
def client(dummy_llm):
    # Override LLM dependency
    app.dependency_overrides[get_llm] = lambda: dummy_llm
    return TestClient(app)

@pytest.fixture()
def patch_policy_timeout(monkeypatch):
    """Force a very small per-tool timeout via policy.defaults()."""
    from apps.orchestrator import policy as polmod
    orig = policy.defaults
    def tiny_defaults():
        d = orig() or {}
        d = dict(d)
        d["max_tool_runtime_sec"] = 1
        return d
    monkeypatch.setattr(polmod.policy, "defaults", tiny_defaults)
    monkeypatch.setattr(policy, "defaults", tiny_defaults)
    yield
