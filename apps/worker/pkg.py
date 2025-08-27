# apps/worker/pkg.py
from __future__ import annotations
from typing import Dict, Any, Optional
from .terminal import terminal_run

async def pkg_install(id: str, manager: str = "winget", version: Optional[str] = None,
                      silent: bool = True, dry_run: bool = True) -> Dict[str, Any]:
    if manager == "winget":
        cmd = f'winget install --id "{id}"'
        if version: cmd += f' --version "{version}"'
        if silent: cmd += " --silent --accept-package-agreements --accept-source-agreements"
    elif manager == "choco":
        cmd = f'choco install {id} -y'
    else:
        return {"ok": False, "error": f"manager_not_supported:{manager}"}
    if dry_run: return {"ok": True, "dry_run": True, "cmd": cmd}
    return await terminal_run(cmd, shell="powershell", timeout_sec=600)

async def pkg_uninstall(id: str, manager: str = "winget", dry_run: bool = True) -> Dict[str, Any]:
    if manager == "winget":
        cmd = f'winget uninstall --id "{id}" --silent'
    elif manager == "choco":
        cmd = f'choco uninstall {id} -y'
    else:
        return {"ok": False, "error": f"manager_not_supported:{manager}"}
    if dry_run: return {"ok": True, "dry_run": True, "cmd": cmd}
    return await terminal_run(cmd, shell="powershell", timeout_sec=600)

async def pkg_ensure(id: str, manager: str = "winget", version: Optional[str] = None,
                     dry_run: bool = True) -> Dict[str, Any]:
    # naive ensure: try install; real impl could probe installed versions
    return await pkg_install(id=id, manager=manager, version=version, dry_run=dry_run)
