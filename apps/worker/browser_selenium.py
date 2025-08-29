# apps/worker/browser_selenium.py - Windows fallback using Selenium
from __future__ import annotations
import os
import time
from typing import Dict, Any

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

def _get_chrome_options(headless: bool = False) -> Options:
    """Configure Chrome options"""
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-web-security")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--disable-extensions")
    return options

def browser_nav_selenium(url: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    """Navigate using Selenium WebDriver"""
    if not SELENIUM_AVAILABLE:
        return {"ok": False, "error": "selenium_not_installed"}
    
    try:
        options = _get_chrome_options(headless)
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        title = driver.title
        driver.quit()
        return {"ok": True, "url": url, "title": title}
    except Exception as e:
        return {"ok": False, "error": f"selenium_nav_error: {str(e)}"}

def browser_click_selenium(selector: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    """Click element using Selenium"""
    if not SELENIUM_AVAILABLE:
        return {"ok": False, "error": "selenium_not_installed"}
    
    try:
        options = _get_chrome_options(headless)
        driver = webdriver.Chrome(options=options)
        
        # Wait for element and click
        wait = WebDriverWait(driver, 15)
        element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
        element.click()
        
        driver.quit()
        return {"ok": True, "selector": selector}
    except TimeoutException:
        return {"ok": False, "error": f"element_not_found: {selector}"}
    except Exception as e:
        return {"ok": False, "error": f"selenium_click_error: {str(e)}"}

def browser_type_selenium(selector: str, text: str, profile: str = "default", 
                         clear: bool = False, press_enter: bool = False, headless: bool = False) -> Dict[str, Any]:
    """Type text using Selenium"""
    if not SELENIUM_AVAILABLE:
        return {"ok": False, "error": "selenium_not_installed"}
    
    try:
        options = _get_chrome_options(headless)
        driver = webdriver.Chrome(options=options)
        
        # Wait for element
        wait = WebDriverWait(driver, 15)
        element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        
        if clear:
            element.clear()
        
        element.send_keys(text)
        
        if press_enter:
            from selenium.webdriver.common.keys import Keys
            element.send_keys(Keys.RETURN)
        
        driver.quit()
        return {"ok": True, "selector": selector, "typed": len(text)}
    except Exception as e:
        return {"ok": False, "error": f"selenium_type_error: {str(e)}"}

def browser_wait_ms_selenium(ms: int = 500) -> Dict[str, Any]:
    """Simple wait"""
    time.sleep(max(ms, 0) / 1000.0)
    return {"ok": True, "waited_ms": ms}

def browser_eval_selenium(js: str, profile: str = "default", headless: bool = False) -> Dict[str, Any]:
    """Execute JavaScript using Selenium"""
    if not SELENIUM_AVAILABLE:
        return {"ok": False, "error": "selenium_not_installed"}
    
    try:
        options = _get_chrome_options(headless)
        driver = webdriver.Chrome(options=options)
        
        result = driver.execute_script(js)
        driver.quit()
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": f"selenium_eval_error: {str(e)}"}