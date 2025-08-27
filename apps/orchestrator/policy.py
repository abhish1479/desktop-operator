from __future__ import annotations
import os, re, socket, yaml, fnmatch
from pathlib import Path
from typing import Dict, Any, List, Tuple

class Policy:
    def __init__(self, config_path: str = "config/guardrails.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg: Dict[str, Any] = yaml.safe_load(f) or {}

    # ---------- high level gates ----------
    def sandbox_guard(self, target_path: str) -> Tuple[bool, str]:
        sandboxes: List[str] = self.cfg.get("path_sandboxes", [])
        path = Path(os.path.expandvars(target_path)).resolve()
        for sb in sandboxes:
            root = Path(os.path.expandvars(sb)).resolve()
            try:
                path.relative_to(root)
                return True, ""
            except ValueError:
                continue
        return False, f"Write outside sandbox not allowed: {path}"

    def require_approval(self, category: str) -> bool:
        rc = self.cfg.get("risk_categories", {}).get(category, {})
        return bool(rc.get("approval_required", False))

    # ---------- exec rules ----------
    def is_exec_allowed(self, bin_name: str, args: List[str]) -> Tuple[bool, str]:
        allow_exec = self.cfg.get("allow_exec", {})
        if bin_name not in allow_exec:
            return False, f"Exec denied for {bin_name}"
        if bin_name == "winget":
            # naive vendor/package checks; expand as needed
            ids_allow = set(allow_exec["winget"].get("ids_allow", []))
            if ids_allow:
                for a in args:
                    if any(i in a for i in ids_allow):
                        return True, ""
                return False, "winget: package id not in allow-list"
        return True, ""

    # ---------- network rules ----------
    def is_host_allowed(self, host: str, port: int) -> bool:
        allowed = self.cfg.get("network_allow", [])
        label = f"{host}:{port}"
        return label in allowed or any(label.endswith(a) for a in allowed)

    # ---------- tool caps ----------
    def tool_caps(self, tool: str) -> Dict[str, Any]:
        return self.cfg.get("tools", {}).get(tool, {})

    def defaults(self) -> Dict[str, Any]:
        return self.cfg.get("defaults", {})

policy = Policy()
