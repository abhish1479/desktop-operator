# apps/worker/browser_sync.py
from __future__ import annotations
import os
from typing import Dict, Any
from playwright.sync_api import sync_playwright

def browser_nav_sync(url: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    """Synchronous browser navigation - Windows fallback"""
    profile_dir = f"data/playwright-profiles/{profile}"
    os.makedirs(profile_dir, exist_ok=True)
    
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-web-security"]
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = page.title()
            context.close()
            return {"ok": True, "url": url, "title": title}
    except Exception as e:
        return {"ok": False, "error": f"sync_nav_error: {str(e)}"}

def browser_click_sync(selector: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    """Synchronous browser click"""
    profile_dir = f"data/playwright-profiles/{profile}"
    
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.click(selector, timeout=15000)
            context.close()
            return {"ok": True, "selector": selector}
    except Exception as e:
        return {"ok": False, "error": f"sync_click_error: {str(e)}"}

def browser_type_sync(selector: str, text: str, profile: str = "default", 
                     clear: bool = False, press_enter: bool = False, headless: bool = False) -> Dict[str, Any]:
    """Synchronous browser typing"""
    profile_dir = f"data/playwright-profiles/{profile}"
    
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.wait_for_selector(selector, timeout=15000)
            if clear:
                page.fill(selector, "")
            page.type(selector, text, delay=20)
            if press_enter:
                page.keyboard.press("Enter")
            context.close()
            return {"ok": True, "selector": selector, "typed": len(text)}
    except Exception as e:
        return {"ok": False, "error": f"sync_type_error: {str(e)}"}

def browser_wait_ms_sync(ms: int = 500) -> Dict[str, Any]:
    """Synchronous wait"""
    import time
    time.sleep(max(ms, 0) / 1000.0)
    return {"ok": True, "waited_ms": ms}

def browser_eval_sync(js: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    """Synchronous JavaScript execution"""
    profile_dir = f"data/playwright-profiles/{profile}"
    
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = context.pages[0] if context.pages else context.new_page()
            result = page.evaluate(js)
            context.close()
            return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": f"sync_eval_error: {str(e)}"}