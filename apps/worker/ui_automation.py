# apps/worker/ui_automation.py
import time
import pywinauto
from pywinauto.application import Application
from pywinauto.findwindows import find_windows

def window_focus(title_re: str) -> dict:
    try:
        handles = find_windows(title_re=title_re)
        if not handles: return {"ok": False, "error":"window_not_found"}
        app = Application(backend="uia").connect(handle=handles[0])
        dlg = app.window(handle=handles[0])
        dlg.set_focus()
        return {"ok": True, "title": dlg.window_text()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def ui_click(name: str, control_type: str="Button") -> dict:
    try:
        app = Application(backend="uia").connect(active_only=True)
        dlg = app.top_window()
        ctrl = dlg.child_window(title=name, control_type=control_type)
        ctrl.wait("enabled", timeout=5)
        ctrl.click_input()
        return {"ok": True, "clicked": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def ui_type(text: str) -> dict:
    try:
        app = Application(backend="uia").connect(active_only=True)
        dlg = app.top_window()
        dlg.type_keys(text, with_spaces=True, set_foreground=True)
        return {"ok": True, "typed": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def ui_menu_select(path: str) -> dict:
    try:
        app = Application(backend="uia").connect(active_only=True)
        dlg = app.top_window()
        dlg.menu_select(path)  # e.g., "File->Save As..."
        return {"ok": True, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e)}
