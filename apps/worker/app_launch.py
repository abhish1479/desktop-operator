import subprocess, shutil, os, sys

ALLOWED = {
    "whatsapp": 'Start-Process "whatsapp:"',
    # add more mappings as needed
}

def launch(name: str) -> dict:
    cmd = ALLOWED.get(name.lower())
    if not cmd:
        return {"ok": False, "error": f"app_not_allowed: {name}"}
    try:
        subprocess.Popen(["pwsh","-NoLogo","-NoProfile","-Command", cmd])
        return {"ok": True, "launched": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}
