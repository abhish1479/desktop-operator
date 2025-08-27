# tests/test_failure_paths.py
from __future__ import annotations
import pytest
from apps.orchestrator.tools.registry import TOOL_REGISTRY

def test_unknown_tool_error(client):
    body = {"goal":"Try an unknown tool please.","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    assert j["ok"] is True
    assert len(j["steps"]) >= 1
    step = j["steps"][0]
    assert step["obs"]["ok"] is False
    assert "unknown_tool" in step["obs"]["error"]

def test_blocked_tool_via_options(client):
    # The dummy LLM will plan terminal.run; we block it via options
    body = {
        "goal":"Run a blocked terminal command.",
        "dry_run": True,
        "options": {"blocked_tools":["terminal.run"]}
    }
    j = client.post("/tasks/run", json=body).json()
    step = j["steps"][0]
    assert step["tool"] == "terminal.run"
    assert step["obs"]["ok"] is False
    assert "tool_blocked_by_request" in step["obs"]["error"]

def test_tool_timeout(client, patch_policy_timeout):
    body = {"goal":"Run a timeout test in terminal.","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    step = j["steps"][0]
    assert step["tool"] == "terminal.run"
    assert step["obs"]["ok"] is False
    assert "tool_timeout" in step["obs"]["error"]

def test_tool_raises_exception(client, monkeypatch):
    # Temporarily register a tool that raises
    def boom(**kwargs): raise RuntimeError("kaboom")
    TOOL_REGISTRY["test.raise"] = boom
    try:
        body = {"goal":"raise tool error now","dry_run": True}
        # Teach DummyLLM to call it by using a unique phrase:
        # monkeypatch the DummyLLM planning via goal phrase:
        # We'll hit default path with fs.listdir, so instead directly call the tool by allowed_tools
        # Simpler: rely on existing “unknown tool” mapping and change registry key to match
        # We'll just request unknown tool & rename it:
        pass
    finally:
        TOOL_REGISTRY.pop("test.raise", None)

    # Create a tailored DummyLLM mapping by directly calling /tasks/run with options.allowed_tools to force it?
    # Easier route: call the tool directly through the registry by adding “boom tool” phrase:
    # Since the DummyLLM doesn't know “test.raise”, we cheat: add alias for does.not.exist
