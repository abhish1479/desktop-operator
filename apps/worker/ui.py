# apps/worker/ui.py
from __future__ import annotations
import time, re
from typing import Dict, Any, Optional

# Safe import of uiautomation
try:
    import uiautomation as auto  # type: ignore
except Exception:  # ImportError or other environment errors
    auto = None  # sentinel; functions will report dependency error

def _dep_missing() -> Dict[str, Any]:
    return {"ok": False, "error": "uiautomation_not_installed"}


def ui_focus(title_re: str, timeout_sec: int = 5) -> Dict[str, Any]:
    if auto is None:
        return _dep_missing()
    deadline = time.time() + timeout_sec
    pat = re.compile(title_re)
    while time.time() < deadline:
        for w in auto.GetRootControl().GetChildren():
            if getattr(w, "ControlTypeName", "") == "WindowControl":
                title = getattr(w, "Name", "") or ""
                if pat.search(title):
                    w.SetActive(); return {"ok": True, "title": title}
        time.sleep(0.2)
    return {"ok": False, "error": "window_not_found"}


def ui_find(name: str = "", control_type: str = "", timeout_sec: int = 5) -> Dict[str, Any]:
    if auto is None:
        return _dep_missing()
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ctrl = auto.ControlFromPoint(auto.GetCursorPos())
        # simple placeholder: return focused control info
        fc = auto.GetFocusedControl()
        if fc:
            return {"ok": True, "name": fc.Name, "type": fc.ControlTypeName}
        time.sleep(0.2)
    return {"ok": False, "error": "not_found"}


def ui_click(name: str, control_type: str = "ButtonControl", timeout_sec: int = 5) -> Dict[str, Any]:
    if auto is None:
        return _dep_missing()
    root = auto.GetRootControl()
    ctrl = root.Control(searchDepth=8, Name=name, ControlType=control_type)
    if not ctrl.Exists(0.5):
        return {"ok": False, "error": "control_not_found", "name": name, "type": control_type}
    ctrl.Click()
    return {"ok": True}


def ui_type(text: str) -> Dict[str, Any]:
    if auto is None:
        return _dep_missing()
    auto.SendKeys(text); return {"ok": True}


def ui_shortcut(keys: str) -> Dict[str, Any]:
    if auto is None:
        return _dep_missing()
    # e.g., "Ctrl+F", "Alt+F4"
    ks = keys.replace("+", "}{").join(["{", "}"])
    auto.SendKeys(ks)
    return {"ok": True}


def ui_menu_select(path: str) -> Dict[str, Any]:
    if auto is None:
        return _dep_missing()
    # 'File->Open' heuristic: send Alt shortcuts
    for part in path.split("->"):
        auto.SendKeys("%" + part[0])  # Alt + first letter
        time.sleep(0.2)
    return {"ok": True}


def ui_wait(name: str, control_type: str = "TextControl", state: str = "exists", timeout_sec: int = 10) -> Dict[str, Any]:
    if auto is None:
        return _dep_missing()
    root = auto.GetRootControl()
    ctrl = root.Control(searchDepth=10, Name=name, ControlType=control_type)
    ok = ctrl.Exists(timeout_sec)
    if state == "exists": return {"ok": ok}
    return {"ok": False, "error": "unsupported_state"}
