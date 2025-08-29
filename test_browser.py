import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.getcwd())

async def test_browser_execute():
    try:
        from apps.worker.browser_actions import browser_execute
        
        actions = [
            {"op": "goto", "params": {"url": "https://www.youtube.com"}}
        ]
        
        print("Testing browser_execute...")
        result = await browser_execute(actions)  # Now properly awaited
        print("browser_execute result:", result)
        return result
        
    except Exception as e:
        print("Error testing browser_execute:", e)
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    result = asyncio.run(test_browser_execute())
    print("Final result:", result)
