from __future__ import annotations
import os, subprocess, shutil
from typing import Dict, Any, List, Optional
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


def _find_code_cli() -> str:
    """
    Try to locate VS Code's CLI. Prefer PATH, otherwise common Windows locations.
    Returns the executable to invoke (e.g., 'code' or absolute path to code.cmd).
    """
    # If available on PATH, use it
    if shutil.which("code"):
        return "code"

    # Typical Windows install
    user_profile = os.environ.get("USERPROFILE") or ""
    candidate = os.path.join(user_profile, r"AppData\Local\Programs\Microsoft VS Code\bin\code.cmd")
    if os.path.isfile(candidate):
        return candidate

    # System-wide (less common)
    candidate2 = r"C:\Program Files\Microsoft VS Code\bin\code.cmd"
    if os.path.isfile(candidate2):
        return candidate2

    # Insiders (optional)
    if shutil.which("code-insiders"):
        return "code-insiders"
    ins = os.path.join(user_profile, r"AppData\Local\Programs\Microsoft VS Code Insiders\bin\code-insiders.cmd")
    if os.path.isfile(ins):
        return ins

    raise FileNotFoundError("VS Code CLI not found. Ensure 'code' command is installed (VS Code: Command Palette → 'Shell Command: Install 'code' command').")

def vscode_install_extension(ext_id: str, force: bool = False) -> Dict[str, Any]:
    """
    Install a VS Code extension by Marketplace identifier, e.g.:
      - 'Dart-Code.dart-code'
      - 'Dart-Code.flutter'
      - 'ms-python.python'
      - 'ms-vscode.cpptools'
    """
    cli = _find_code_cli()
    args = [cli, "--install-extension", ext_id]
    if force:
        args.append("--force")

    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "code": proc.returncode,
            "stdout": (proc.stdout or "")[:10000],
            "stderr": (proc.stderr or "")[:10000],
            "ext_id": ext_id,
        }
    except FileNotFoundError as e:
        return {"ok": False, "error": f"code_cli_not_found: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"vscode_install_extension_error: {e}"}