# apps/worker/terminal.py
from __future__ import annotations
import asyncio, os
from typing import Dict, Any, Optional

async def terminal_run(cmd: str, shell: str = "powershell", timeout_sec: int = 120,
                       cwd: Optional[str] = None, env: Optional[dict] = None) -> Dict[str, Any]:
    if shell.lower() in ("powershell", "pwsh"):
        full_cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]
    elif shell.lower() == "cmd":
        full_cmd = ["cmd", "/c", cmd]
    elif shell.lower() in ("bash","wsl"):
        full_cmd = ["bash", "-lc", cmd]
    else:
        full_cmd = [shell, "-lc", cmd]

    proc = await asyncio.create_subprocess_exec(
        *full_cmd, cwd=cwd, env={**os.environ, **(env or {})},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        return {"ok": False, "error": f"timeout_{timeout_sec}s"}
    rc = proc.returncode
    return {"ok": rc == 0, "code": rc, "stdout": out.decode(errors="ignore"), "stderr": err.decode(errors="ignore")}
