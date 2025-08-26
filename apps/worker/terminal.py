import subprocess, platform

def run_cmd(cmd: str, shell: str = "powershell", timeout_sec: int = 120) -> dict:
    try:
        if shell == "powershell" and platform.system() == "Windows":
            args = ["pwsh","-NoLogo","-NoProfile","-Command", cmd]
        else:
            args = ["bash","-lc", cmd]
        out = subprocess.run(args, capture_output=True, text=True, timeout=timeout_sec)
        return {
            "ok": out.returncode == 0,
            "code": out.returncode,
            "stdout": out.stdout,
            "stderr": out.stderr
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "timeout_sec": timeout_sec}
    except Exception as e:
        return {"ok": False, "error": str(e)}
