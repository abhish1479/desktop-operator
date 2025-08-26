import os, requests, subprocess

BRIDGE = os.getenv("VSCODE_BRIDGE_URL", "http://127.0.0.1:48100")

def vscode_open(path: str, line: int | None = None) -> dict:
    try:
        args = ["code"]
        if line: args += ["-g", f"{path}:{line}"]
        else: args += [path]
        subprocess.Popen(args)
        return {"ok": True, "path": path, "line": line}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def vscode_save_all() -> dict:
    try:
        r = requests.post(f"{BRIDGE}/saveAll", timeout=3)
        return {"ok": r.status_code == 200, "status": r.status_code, "body": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def vscode_get_diagnostics() -> dict:
    try:
        r = requests.get(f"{BRIDGE}/diagnostics", timeout=3)
        if r.ok:
            return {"ok": True, "diagnostics": r.json()}
        return {"ok": False, "status": r.status_code, "body": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}
