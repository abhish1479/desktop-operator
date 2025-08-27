# apps/worker/skills/whatsapp_chat.py
import os, time, asyncio
from typing import List, Dict, Optional
from playwright.async_api import async_playwright

# Primary selectors (WhatsApp Web changes often; these work today)
SEL_SEARCH = "div[contenteditable='true'][data-tab='3'], div[contenteditable='true'][aria-label*='Search']"
SEL_MSG_IN  = "div.message-in span.selectable-text, div.message-in div[dir='ltr']"
SEL_MSG_BOX = "div[contenteditable='true'][data-tab='10'], div[contenteditable='true'][aria-label*='Type a message']"

async def _launch_with_profile(profile_dir: str):
    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        accept_downloads=True,
    )
    page = await ctx.new_page()
    return pw, ctx, page

async def _open_chat(page, contact: str):
    # Wait for WhatsApp Web shell
    await page.goto("https://web.whatsapp.com")
    await page.wait_for_load_state("domcontentloaded")
    # Search box and open contact
    sb = await page.wait_for_selector(SEL_SEARCH, timeout=120_000)  # allow time for QR/login first time
    await sb.fill(contact)
    await sb.press("Enter")
    # Wait for message box in chat
    await page.wait_for_selector(SEL_MSG_BOX, timeout=30_000)

async def _send_message(page, text: str):
    box = await page.wait_for_selector(SEL_MSG_BOX, timeout=30_000)
    await box.type(text)
    await box.press("Enter")

async def run_chat(contact: str,
                   profile_dir: str,
                   initial_message: Optional[str],
                   duration_sec: int = 120,
                   allow_llm: bool = True) -> Dict:
    """
    Chat with a contact for `duration_sec`, auto-replying via LLM if available (OPENAI_API_KEY),
    else fallback to a simple echo.
    """
    from datetime import datetime, timedelta
    transcript: List[Dict] = []
    pw = ctx = page = None
    try:
        pw, ctx, page = await _launch_with_profile(profile_dir)
        await _open_chat(page, contact)

        if initial_message:
            await _send_message(page, initial_message)
            transcript.append({"role": "assistant", "text": initial_message, "t": time.time()})

        # optional LLM
        client = None
        if allow_llm and os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                client = OpenAI()
            except Exception:
                client = None

        end_at = datetime.utcnow() + timedelta(seconds=duration_sec)
        last_seen_text = None

        while datetime.utcnow() < end_at:
            # Read latest incoming message
            msgs = await page.query_selector_all(SEL_MSG_IN)
            if msgs:
                txt = (await msgs[-1].inner_text()).strip()
                if txt and txt != last_seen_text:
                    last_seen_text = txt
                    transcript.append({"role": "user", "text": txt, "t": time.time()})

                    # Compose reply
                    if client:
                        prompt = [
                            {"role": "system", "content": "You're a concise, friendly personal assistant. Keep replies under 2 lines."},
                            {"role": "user", "content": txt}
                        ]
                        try:
                            resp = client.chat.completions.create(
                                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                                messages=prompt,
                                temperature=0.4,
                            )
                            reply = (resp.choices[0].message.content or "").strip()
                        except Exception as e:
                            reply = f"Got it: {txt[:140]}"
                    else:
                        reply = f"Got it: {txt[:140]}"

                    await _send_message(page, reply)
                    transcript.append({"role": "assistant", "text": reply, "t": time.time()})

            await page.wait_for_timeout(2000)  # 2s poll

        return {"ok": True, "contact": contact, "duration_sec": duration_sec, "messages": transcript[-30:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            if ctx: await ctx.close()
            if pw: await pw.stop()
        except Exception:
            pass
