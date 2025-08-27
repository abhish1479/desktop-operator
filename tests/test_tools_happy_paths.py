# tests/test_tools_happy_paths.py
from __future__ import annotations

def test_fs_create_move_list(client):
    body = {
        "goal": "Create a file and then move it somewhere and list the sandbox folder.",
        "dry_run": True
    }
    r = client.post("/tasks/run", json=body)
    j = r.json()
    assert j["ok"] is True
    assert any(s["tool"].startswith("fs.") for s in j["steps"])
    # success observations
    oks = [s["obs"].get("ok") for s in j["steps"]]
    assert all(oks)

def test_terminal_echo(client):
    body = {"goal":"In terminal, echo a short message.","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    step = j["steps"][0]
    assert step["tool"] == "terminal.run"
    assert step["obs"]["ok"] is True
    assert "hello-from-terminal" in step["obs"]["stdout"].lower()

def test_http_get(client):
    body = {"goal":"Do an HTTP GET to example.com.","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    step = j["steps"][0]
    assert step["tool"] == "http.request"
    assert step["obs"]["ok"] is True
    assert step["obs"]["status"] == 200

def test_csv_write_read(client):
    body = {"goal":"Write a CSV and then read it back.","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    tools = [s["tool"] for s in j["steps"]]
    assert "data.csv.write" in tools and "data.csv.read" in tools
    read = [s for s in j["steps"] if s["tool"] == "data.csv.read"][0]
    assert read["obs"]["ok"] is True
    assert read["obs"]["count"] == 2

def test_json_write_read(client):
    body = {"goal":"Write a JSON file and read it back.","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    assert any(s["tool"] == "data.json.write" for s in j["steps"])
    assert any(s["tool"] == "data.json.read" for s in j["steps"])
    js = [s for s in j["steps"] if s["tool"] == "data.json.read"][0]["obs"]
    assert js["ok"] is True
    assert js["data"]["ok"] is True

def test_pkg_install_dry_run(client):
    body = {"goal":"Install Git using the package manager (dry run).","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    step = j["steps"][0]
    assert step["tool"] == "pkg.install"
    assert step["obs"]["ok"] is True
    assert step["obs"]["dry_run"] is True

def test_vscode_open_smoke(client):
    body = {"goal":"Open VS Code on a file just to smoke test.","dry_run": True}
    j = client.post("/tasks/run", json=body).json()
    assert any(s["tool"] == "vscode.open" for s in j["steps"])
