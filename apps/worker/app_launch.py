import subprocess, shutil, os, sys
import webbrowser

ALLOWED = {
    "whatsapp": 'Start-Process "whatsApp:"',
    # add more mappings as needed
}

def launch(name: str) -> dict:
    print(f"app_launch: trying to launch '{name}'")
    cmd = ALLOWED.get(name.lower())
    if not cmd:
        print(f"app_launch: '{name}' not in ALLOWED list")
        return {"ok": False, "error": f"app_not_allowed: {name}"}
    
    print(f"app_launch: command = '{cmd}'")
    
    # Try multiple methods for WhatsApp
    if name.lower() == "whatsapp":
        # Method 1: Try webbrowser.open (works for URI schemes)
        try:
            print("app_launch: trying webbrowser.open('whatsapp:')")
            webbrowser.open("whatsapp:")
            print("app_launch: webbrowser.open succeeded")
            return {"ok": True, "launched": name, "method": "webbrowser"}
        except Exception as e:
            print(f"app_launch: webbrowser.open failed: {e}")
        
        # Method 2: Try with 'powershell' instead of 'pwsh'
        try:
            print("app_launch: trying powershell Start-Process")
            subprocess.Popen(["powershell", "-NoLogo", "-NoProfile", "-Command", cmd])
            print("app_launch: powershell succeeded")
            return {"ok": True, "launched": name, "method": "powershell"}
        except Exception as e:
            print(f"app_launch: powershell failed: {e}")
        
        # Method 3: Try with 'pwsh' (original)
        try:
            print("app_launch: trying pwsh Start-Process")
            subprocess.Popen(["pwsh", "-NoLogo", "-NoProfile", "-Command", cmd])
            print("app_launch: pwsh succeeded")
            return {"ok": True, "launched": name, "method": "pwsh"}
        except Exception as e:
            print(f"app_launch: pwsh failed: {e}")
        
        # Method 4: Try direct subprocess with shell=True
        try:
            print("app_launch: trying shell=True")
            subprocess.Popen(f'start "" "whatsapp:"', shell=True)
            print("app_launch: shell=True succeeded")
            return {"ok": True, "launched": name, "method": "shell"}
        except Exception as e:
            print(f"app_launch: shell=True failed: {e}")
        
        print("app_launch: all methods failed")
        return {"ok": False, "error": "all_launch_methods_failed"}
    
    # For other apps, try the original method
    try:
        subprocess.Popen(["powershell", "-NoLogo", "-NoProfile", "-Command", cmd])
        return {"ok": True, "launched": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}
