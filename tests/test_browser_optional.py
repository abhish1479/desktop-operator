# tests/test_browser_optional.py
import os
import pytest

RUN = os.getenv("RUN_BROWSER_TESTS", "0") == "1"

@pytest.mark.skipif(not RUN, reason="Enable with RUN_BROWSER_TESTS=1 (requires Playwright, Windows session)")
def test_youtube_minimal(client):
    body = {
        "goal":"Open browser and play a YouTube song video (saiyaara 1980 kishore kumar).",
        "dry_run": False,
        "options": {"profile":"default","max_steps":10}
    }
    j = client.post("/tasks/run", json=body).json()
    # Should have at least one browser.execute step
    tools = [s["tool"] for s in j["steps"]]
    assert "browser.execute" in tools
    # Final eval or click should be ok=True
    oks = [s["obs"].get("ok") for s in j["steps"]]
    assert any(oks)
