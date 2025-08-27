# apps/worker/skills/whatsapp_desktop_chat.py
from __future__ import annotations
import os, time, subprocess, datetime, hashlib
from typing import Optional, Dict, Any, List

import uiautomation as auto
import pyperclip
from typing import Optional, Dict, Any, List  # <- Any included

from typing import Tuple
try:
    from PIL import ImageGrab  # pip install pillow
    import pytesseract         # pip install pytesseract  (and install Tesseract engine)
except Exception:
    ImageGrab = None
    pytesseract = None

# ----------------- small helpers -----------------
def _log(logs: List[str], msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{ts}] {msg}")

    

def _hotkey(*keys: str, pause: float = 0.05):
    seq = "".join("{" + k + "}" for k in keys)   # e.g. {Ctrl}{f}
    auto.SendKeys(seq)
    time.sleep(pause)

def _exit_search_mode(win, logs: list[str]):
    # close search overlays / clear focus
    _hotkey("ESC"); _hotkey("ESC")
    rect = win.BoundingRectangle
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    auto.Click(cx, cy)  # click chat area
    time.sleep(0.15)
    _log(logs, "Exited search mode")

def _click_composer_area(win, logs: list[str]):
    rect = win.BoundingRectangle
    x = rect.left + 300
    y = rect.bottom - 50          # bottom bar where the input sits
    auto.Click(x, y)
    time.sleep(0.1)
    _log(logs, "Clicked composer area")

def _ensure_composer_focus(win, logs: list[str]):
    # If focus is on Search, exit it
    try:
        fc = auto.GetFocusedControl()
        if fc and fc.ControlTypeName == "EditControl" and ("Search" in (fc.Name or "") or "Find" in (fc.Name or "")):
            _exit_search_mode(win, logs)
    except Exception:
        pass

    # Prefer the real Edit control
    edit = win.EditControl(RegexName=r"(Type a message.*|Message.*)", searchDepth=20)
    if edit.Exists(0.3):
        edit.SetFocus()
        _log(logs, "Composer focused (EditControl)")
        return edit

    # Fallback: click near bottom to give focus, then re-try
    _click_composer_area(win, logs)
    edit = win.EditControl(RegexName=r"(Type a message.*|Message.*)", searchDepth=20)
    if edit.Exists(0.2):
        edit.SetFocus()
        _log(logs, "Composer focused after click")
        return edit
    _log(logs, "Composer focus uncertain")
    return None

def _fingerprint(s: Optional[str]) -> str:
    if not s:
        return ""
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:10]

# ----------------- WhatsApp window ops -----------------
def _launch_or_focus_whatsapp(logs: List[str], wait_s: float = 8.0):
    win = auto.WindowControl(searchDepth=1, Name="WhatsApp")
    if not win.Exists(0.3):
        _log(logs, "WhatsApp not found, launching via URI…")
        try:
            subprocess.Popen('start "" "whatsapp:"', shell=True)
        except Exception as e:
            _log(logs, f"URI launch failed: {e}")
        deadline = time.time() + wait_s
        while time.time() < deadline:
            win = auto.WindowControl(searchDepth=1, Name="WhatsApp")
            if win.Exists(0.5):
                break
            time.sleep(0.2)
    if not win.Exists(0.5):
        raise RuntimeError("WhatsApp window not found")
    win.SetActive()
    win.SetTopmost(True)
    _log(logs, "WhatsApp window active")
    return win

# def _search_and_open_contact(win: auto.WindowControl, contact: str, logs: list[str]):
#     # Try direct ValuePattern on a visible search box
#     search_box = None
#     for pat in [r"Search.*", r"Search or start new chat.*", r"Find.*"]:
#         edit = win.EditControl(RegexName=pat, searchDepth=20)
#         if edit.Exists(0.2):
#             search_box = edit
#             break
#     if search_box:
#         try:
#             search_box.SetFocus()
#             vp = search_box.GetPattern(auto.PatternId.ValuePattern)
#             if vp:
#                 vp.SetValue("")
#                 vp.SetValue(contact)
#                 time.sleep(0.6)
#                 _hotkey("ENTER")
#                 time.sleep(1.2)
#                 _log(logs, f"Opened chat via ValuePattern: {contact}")
#                 _exit_search_mode(win, logs)        # <- leave search
#                 return
#         except Exception:
#             pass

#     # Fallback chord path (curly braces so Ctrl isn’t typed as '^')
#     win.SetActive()
#     _hotkey("Ctrl", "f")
#     time.sleep(0.2)
#     _hotkey("Ctrl", "a"); _hotkey("DEL")
#     auto.SendKeys(contact)
#     time.sleep(0.6)
#     _hotkey("ENTER")
#     time.sleep(1.2)
#     _log(logs, f"Opened chat via Ctrl+F: {contact}")
#     _exit_search_mode(win, logs)                    # <- leave search
#     # Prefer a visible search Edit with ValuePattern (no hotkeys)
#     search_box = None
#     for pat in [r"Search.*", r"Search or start new chat.*", r"Find.*"]:
#         edit = win.EditControl(RegexName=pat, searchDepth=20)
#         if edit.Exists(0.2):
#             search_box = edit
#             break
#     if search_box:
#         try:
#             search_box.SetFocus()
#             vp = search_box.GetPattern(auto.PatternId.ValuePattern)
#             if vp:
#                 vp.SetValue("")  # clear
#                 vp.SetValue(contact)
#                 time.sleep(0.6)
#                 _hotkey("ENTER")
#                 time.sleep(1.2)
#                 _log(logs, f"Opened chat via ValuePattern: {contact}")
#                 return
#         except Exception:
#             pass

#     # Fallback: {Ctrl}f, type, Enter
#     win.SetActive()
#     _hotkey("Ctrl", "f")
#     time.sleep(0.2)
#     _hotkey("Ctrl", "a")
#     _hotkey("DEL")
#     auto.SendKeys(contact)
#     time.sleep(0.6)
#     _hotkey("ENTER")
#     time.sleep(1.2)
#     _log(logs, f"Opened chat via Ctrl+F: {contact}")

def _search_and_open_contact(win: auto.WindowControl, contact: str, logs: list[str], exact: bool = True):
    # 1) Try direct ValuePattern on search box
    search_box = None
    for pat in [r"Search.*", r"Search or start new chat.*", r"Find.*"]:
        edit = win.EditControl(RegexName=pat, searchDepth=20)
        if edit.Exists(0.2):
            search_box = edit
            break

    if search_box:
        try:
            search_box.SetFocus()
            vp = search_box.GetPattern(auto.PatternId.ValuePattern)
            if vp:
                vp.SetValue("")
                vp.SetValue(contact)
                time.sleep(0.5)
                # Click exact result if possible (Enter may pick wrong match)
                if _click_list_item_with_text(win, contact, logs):
                    _exit_search_mode(win, logs)
                else:
                    _hotkey("ENTER")
                    time.sleep(0.8)
                    _exit_search_mode(win, logs)
                _log(logs, f"Opened chat via search: {contact}")
                return
        except Exception:
            pass

    # 2) Fallback: open search overlay and type
    win.SetActive()
    _hotkey("Ctrl", "f")
    time.sleep(0.2)
    _hotkey("Ctrl", "a"); _hotkey("DEL")
    auto.SendKeys(contact)
    time.sleep(0.5)
    if _click_list_item_with_text(win, contact, logs):
        _exit_search_mode(win, logs)
    else:
        _hotkey("ENTER")
        time.sleep(0.8)
        _exit_search_mode(win, logs)
    _log(logs, f"Opened chat via Ctrl+F: {contact}")


def _open_by_phone(phone_e164: str, logs: list[str]) -> bool:
    """
    Try deep-link: whatsapp://send?phone=<E164>
    """
    try:
        subprocess.Popen(f'start "" "whatsapp://send?phone={phone_e164}"', shell=True)
        _log(logs, f"Deep link requested for {phone_e164}")
        time.sleep(1.5)
        return True
    except Exception as e:
        _log(logs, f"Deep link failed: {e}")
        return False


def _focus_composer(win: auto.WindowControl, logs: list[str]):
    edit = win.EditControl(RegexName=r"(Type a message.*|Message.*)", searchDepth=20)
    if edit.Exists(0.5):
        edit.SetFocus()
        _log(logs, "Composer focused")
        return True
    # gentle TAB walk fallback
    for _ in range(6):
        _hotkey("TAB")
        edit = win.EditControl(RegexName=r"(Type a message.*|Message.*)", searchDepth=20)
        if edit.Exists(0.1):
            edit.SetFocus()
            _log(logs, "Composer focused via TAB")
            return True
    _log(logs, "Composer focus uncertain")
    return False

# def _send_text(win: auto.WindowControl, text: str, logs: list[str]):
#     edit = _ensure_composer_focus(win, logs)

#     # Try ValuePattern if available (cleanest)
#     if edit:
#         try:
#             vp = edit.GetPattern(auto.PatternId.ValuePattern)
#             if vp:
#                 vp.SetValue(text)
#                 time.sleep(0.05)
#                 _hotkey("ENTER")
#                 _log(logs, f"Sent (ValuePattern): {text[:80]}{'...' if len(text)>80 else ''}")
#                 return
#         except Exception:
#             pass

#     # Fallback: plain typing into focused composer
#     auto.SendKeys(text)
#     time.sleep(0.05)
#     _hotkey("ENTER")
#     _log(logs, f"Sent (typed): {text[:80]}{'...' if len(text)>80 else ''}")
#     edit = _ensure_composer_focus(win, logs)

#     # Try ValuePattern if available (cleanest)
#     if edit:
#         try:
#             vp = edit.GetPattern(auto.PatternId.ValuePattern)
#             if vp:
#                 vp.SetValue(text)
#                 time.sleep(0.05)
#                 _hotkey("ENTER")
#                 _log(logs, f"Sent (ValuePattern): {text[:80]}{'...' if len(text)>80 else ''}")
#                 return
#         except Exception:
#             pass

#     # Fallback: plain typing into focused composer
#     auto.SendKeys(text)
#     time.sleep(0.05)
#     _hotkey("ENTER")
#     _log(logs, f"Sent (typed): {text[:80]}{'...' if len(text)>80 else ''}")
#     edit = win.EditControl(RegexName=r"(Type a message.*|Message.*)", searchDepth=20)
#     if edit.Exists(0.2):
#         try:
#             edit.SetFocus()
#             vp = edit.GetPattern(auto.PatternId.ValuePattern)
#             if vp:  # cleanest path
#                 vp.SetValue(text)
#                 time.sleep(0.05)
#                 _hotkey("ENTER")
#                 _log(logs, f"Sent (ValuePattern): {text[:80]}{'...' if len(text)>80 else ''}")
#                 return
#         except Exception:
#             pass
#     _focus_composer(win, logs)
#     auto.SendKeys(text)
#     time.sleep(0.05)
#     _hotkey("ENTER")
#     _log(logs, f"Sent (typed): {text[:80]}{'...' if len(text)>80 else ''}")

def _send_text(win: auto.WindowControl, text: str, logs: list[str], locked_contact: str | None = None, exact: bool = True):
    # Verify we are in the right chat
    if locked_contact:
        title = _current_chat_title(win) or ""
        if not _names_match(title, locked_contact, exact=exact):
            _log(logs, f"Refusing to send: current chat '{title}' != locked '{locked_contact}'")
            return  # hard stop

    edit = _ensure_composer_focus(win, logs)
    if edit:
        try:
            vp = edit.GetPattern(auto.PatternId.ValuePattern)
            if vp:
                vp.SetValue(text)
                time.sleep(0.05)
                _hotkey("ENTER")
                _log(logs, f"Sent (ValuePattern): {text[:80]}{'...' if len(text)>80 else ''}")
                return
        except Exception:
            pass
    auto.SendKeys(text)
    time.sleep(0.05)
    _hotkey("ENTER")
    _log(logs, f"Sent (typed): {text[:80]}{'...' if len(text)>80 else ''}")


def _last_message_text(win: auto.WindowControl) -> Optional[str]:
    # Heuristic: last list item/bubble text
    pane = win.ListControl(searchDepth=10)
    if pane and pane.Exists(0.2):
        try:
            children = pane.GetChildren()
            if children:
                last = children[-1]
                name = last.Name
                if not name:
                    texts = [c.Name for c in last.GetChildren() if getattr(c, "ControlTypeName", "") == "TextControl"]
                    name = " ".join([t for t in texts if t])
                return name or None
        except Exception:
            pass
    try:
        texts = [c for c in win.GetChildren() if getattr(c, "ControlTypeName", "") == "TextControl"]
        if texts:
            return texts[-1].Name or None
    except Exception:
        pass
    return None

# ----------------- LLM helpers -----------------
def _llm_generate(llm: Any, system: str, user: str) -> str:
    if llm is None:
        return ""
    # tolerate different client styles
    if hasattr(llm, "chat"):
        return str(llm.chat(system=system, user=user))
    if hasattr(llm, "generate"):
        return str(llm.generate(f"{system}\n\n{user}"))
    if hasattr(llm, "complete"):
        return str(llm.complete(f"{system}\n\n{user}"))
    return ""

def _compose_system_prompt(
    base: Optional[str],
    topic: Optional[str],
    style: Optional[str],
    max_words: int,
    emoji_ok: bool,
) -> str:
    parts = [
        base or "You are a friendly, concise conversational partner.",
        f"Keep each reply under {max_words} words.",
        "Avoid sending multiple messages in a row.",
    ]
    if style:
        parts.append(f"Style: {style}.")
    if topic:
        parts.append(f"Context to keep in mind: {topic}.")
    parts.append("Be warm and polite.")
    if emoji_ok:
        parts.append("You may use 1 appropriate emoji occasionally.")
    else:
        parts.append("Do not use emojis.")
    return " ".join(parts)

# ----------------- public entrypoint -----------------
# def run_desktop_chat(
#     contact: str,
#     initial_message: Optional[str] = None,
#     duration_sec: int = 120,
#     allow_llm: bool = True,
#     llm: Any = None,
#     # NEW knobs ↓
#     system_prompt: Optional[str] = None,
#     topic: Optional[str] = None,
#     style: Optional[str] = None,      # e.g. "Hinglish (Hindi+English mix), light humorous tone"
#     max_words: int = 40,
#     emoji_ok: bool = True,
# ) -> Dict[str, Any]:
#     """
#     Open WhatsApp Desktop, navigate to contact, send an initial message (generated if not provided),
#     then optionally run an LLM-driven auto-reply loop for `duration_sec`.
#     """
#     logs: List[str] = []
#     SENT_MARK = " [DO]"  # so we don't reply to ourselves

#     win = _launch_or_focus_whatsapp(logs)
#     _search_and_open_contact(win, contact, logs)

#     sys_prompt = _compose_system_prompt(system_prompt, topic, style, max_words, emoji_ok)

#     # Generate opening line if not provided
#     if not initial_message and allow_llm and llm is not None:
#         user = f"Start a friendly chat with {contact}. Begin the conversation aligned to the context above."
#         msg = _llm_generate(llm, sys_prompt, user).strip()
#         if not msg:
#             msg = "Hey! Quick ping—free to chat?"
#         initial_message = msg

#     last_fp = _fingerprint(_last_message_text(win))

#     if initial_message:
#         _send_text(win, f"{initial_message}{SENT_MARK}", logs)
#         time.sleep(0.8)
#         last_fp = _fingerprint(_last_message_text(win))

#     if not allow_llm:
#         return {"ok": True, "mode": "manual", "contact": contact, "logs": logs}

#     start = time.time()
#     turns = 0
#     while (time.time() - start) < duration_sec:
#         time.sleep(2.0)
#         cur_text = _last_message_text(win)
#         cur_fp = _fingerprint(cur_text)
#         if cur_fp == last_fp or not cur_text:
#             continue
#         last_fp = cur_fp

#         if SENT_MARK in (cur_text or ""):
#             continue  # skip our own

#         # Generate reply
#         user = f"Friend said: {cur_text}\nReply appropriately. Keep <= {max_words} words."
#         reply = _llm_generate(llm, sys_prompt, user).strip() if llm else ""
#         if not reply:
#             reply = "Samjha 😊—bol, kya chal raha hai?" if emoji_ok else "Samjha — bol, kya chal raha hai?"
#         _send_text(win, f"{reply}{SENT_MARK}", logs)
#         turns += 1
#         if turns >= 12:
#             _log(logs, "Turn limit reached")
#             break

#     return {
#         "ok": True,
#         "mode": "auto",
#         "contact": contact,
#         "turns": turns,
#         "duration_sec": duration_sec,
#         "style": style,
#         "topic": topic,
#         "max_words": max_words,
#         "emoji_ok": emoji_ok,
#         "logs": logs,
#     }
def run_desktop_chat(
    contact: str | None = None,
    initial_message: Optional[str] = None,
    duration_sec: int = 120,
    allow_llm: bool = True,
    llm: Any = None,
    system_prompt: Optional[str] = None,
    topic: Optional[str] = None,
    style: Optional[str] = None,      # e.g., "Hinglish, light humor"
    max_words: int = 40,
    emoji_ok: bool = True,
    allow_ocr: bool = False,
    contact_exact: bool = True,
    phone_e164: str | None = None,    # e.g., "+91XXXXXXXXXX"
    safe_mode: bool = True,
    strict_llm: bool = True,          # if True, never send non-LLM text
) -> Dict[str, Any]:
    """
    Lock to the intended chat (by name and/or phone), optionally send an LLM-generated opener,
    then auto-reply for `duration_sec` using ONLY the LLM. If LLM produces no text, we skip sending.
    Includes strong safeguards so messages are sent only to the locked chat.
    """
    logs: List[str] = []
    SENT_MARK = " [DO]"  # marker so we never reply to ourselves

    # --- 0) Bring up WhatsApp window ---
    win = _launch_or_focus_whatsapp(logs)

    # --- 1) Lock to chat: deep-link by phone (best), then enforce by display name ---
    if phone_e164:
        try:
            _open_by_phone(phone_e164, logs)
            time.sleep(1.0)
        except Exception as e:
            _log(logs, f"Deep-link attempt failed: {e}")

    if contact:
        _search_and_open_contact(win, contact, logs, exact=contact_exact)

    # Verify we actually locked to intended chat (retry once if needed)
    title = _current_chat_title(win) or ""
    if safe_mode and contact and not _names_match(title, contact, exact=contact_exact):
        _log(logs, f"Lock check failed: current '{title}', expected '{contact}'. Retrying…")
        _search_and_open_contact(win, contact, logs, exact=contact_exact)
        time.sleep(0.4)
        title = _current_chat_title(win) or ""
        if not _names_match(title, contact, exact=contact_exact):
            return {"ok": False, "error": f"chat_lock_failed: current '{title}' != expected '{contact}'", "logs": logs}

    locked_name = contact or (title if title else None)

    # --- 2) Build system prompt & optional opener ---
    sys_prompt = _compose_system_prompt(system_prompt, topic, style, max_words, emoji_ok)

    if initial_message is None and allow_llm and llm is not None:
        opener = ""
        try:
            user_open = f"Start a friendly chat with {contact or (phone_e164 or 'friend')}. Begin aligned to the context above."
            opener = _llm_generate(llm, sys_prompt, user_open).strip()
        except Exception as e:
            _log(logs, f"LLM opener failed: {e}")
        if not opener:
            _log(logs, "LLM returned empty opener; not sending any opener.")
        else:
            initial_message = opener

    # --- 3) Seed fingerprint of last incoming message ---
    last_in_text = _last_incoming_message_text(win, logs, use_ocr=allow_ocr)
    last_fp = _fingerprint(last_in_text)

    # --- 4) Send opener (only if we have one; verify lock before send) ---
    if initial_message:
        # final safety check
        if locked_name and safe_mode:
            current = _current_chat_title(win) or ""
            if not _names_match(current, locked_name, exact=contact_exact):
                _log(logs, f"Refusing to send opener: header '{current}' != '{locked_name}'.")
            else:
                _send_text(win, f"{initial_message}{SENT_MARK}", logs, locked_contact=locked_name, exact=contact_exact)
                time.sleep(0.6)
                last_in_text = _last_incoming_message_text(win, logs, use_ocr=allow_ocr)
                last_fp = _fingerprint(last_in_text)
        else:
            _send_text(win, f"{initial_message}{SENT_MARK}", logs, locked_contact=locked_name, exact=contact_exact)
            time.sleep(0.6)
            last_in_text = _last_incoming_message_text(win, logs, use_ocr=allow_ocr)
            last_fp = _fingerprint(last_in_text)

    # If we’re not auto-replying, we’re done
    if not allow_llm:
        return {"ok": True, "mode": "manual", "contact": contact or title, "logs": logs}

    # --- 5) Auto-reply loop (LLM-only) ---
    turns         = 0
    max_turns     = 12
    deadline      = time.time() + duration_sec
    last_send_ts  = 0.0
    last_reply_fp = ""

    while time.time() < deadline and turns < max_turns:
        # gentle poll; also acts as a minimal cooldown
        time.sleep(0.5)

        # Re-verify lock; re-lock if needed
        if locked_name:
            current = _current_chat_title(win) or ""
            if not _names_match(current, locked_name, exact=contact_exact):
                _log(logs, f"Chat switched to '{current}'. Re-locking…")
                _search_and_open_contact(win, locked_name, logs, exact=contact_exact)
                time.sleep(0.3)
                current = _current_chat_title(win) or ""
                if safe_mode and not _names_match(current, locked_name, exact=contact_exact):
                    _log(logs, "Still not locked; skipping this cycle.")
                    continue

        # Read only *incoming* latest
        cur_text = _last_incoming_message_text(win, logs, use_ocr=allow_ocr)
        cur_fp   = _fingerprint(cur_text)

        # Skip if nothing new
        if not cur_text or cur_fp == last_fp:
            continue
        last_fp = cur_fp

        # Optional: bail out early on conversation-closing phrases
        t = cur_text.lower()
        if any(k in t for k in ("bye", "good night", "goodnight", "gn", "ttyl", "talk later", "thanks, bye")):
            _log(logs, "Detected conversation closure; stopping.")
            break

        # Respect a small send cooldown (avoid rapid-fire)
        if time.time() - last_send_ts < 1.5:
            continue

        # Ask LLM for reply
        user_msg = f"Friend said: {cur_text}\nReply appropriately. Keep <= {max_words} words."
        reply = ""
        try:
            reply = _llm_generate(llm, sys_prompt, user_msg).strip() if llm else ""
        except Exception as e:
            _log(logs, f"LLM reply failed: {e}")

        # Strict LLM mode: never send if empty
        if not reply:
            if strict_llm:
                _log(logs, "LLM returned empty reply; skipping send (strict_llm=True).")
                continue
            else:
                # non-strict mode: ultra-minimal soft fallback (single glyph)
                reply = "…"

        # Sanitize & clamp length
        reply = " ".join(reply.split())  # collapse whitespace/newlines
        if max_words:
            words = reply.split()
            if len(words) > max_words:
                reply = " ".join(words[:max_words])

        if not reply:
            continue

        # Avoid repeating the exact same reply
        reply_fp = _fingerprint(reply)
        if reply_fp == last_reply_fp:
            _log(logs, "Reply identical to last one; skipping.")
            continue

        # Final safety: verify still on locked chat before sending
        if locked_name and safe_mode:
            current = _current_chat_title(win) or ""
            if not _names_match(current, locked_name, exact=contact_exact):
                _log(logs, f"Refusing to send: header now '{current}', expected '{locked_name}'.")
                continue

        _send_text(win, f"{reply}{SENT_MARK}", logs, locked_contact=locked_name, exact=contact_exact)
        last_send_ts  = time.time()
        last_reply_fp = reply_fp
        turns += 1

    return {
        "ok": True,
        "mode": "auto",
        "contact": contact or title,
        "turns": turns,
        "duration_sec": duration_sec,
        "style": style,
        "topic": topic,
        "max_words": max_words,
        "emoji_ok": emoji_ok,
        "allow_ocr": allow_ocr,
        "contact_exact": contact_exact,
        "safe_mode": safe_mode,
        "strict_llm": strict_llm,
        "logs": logs,
    }


def _rect_center_xy(rect):
    return ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)

def _current_chat_title(win) -> str | None:
    """
    Try to read the chat header title (contact/group name) from the top bar.
    Heuristic: pick visible TextControl in the top area, right side of the left panel.
    """
    rect = win.BoundingRectangle
    # assume left panel ~ 280px; top bar ~ first 120px height
    left_boundary = rect.left + int((rect.right - rect.left) * 0.3)
    top_band_bottom = rect.top + 120

    best = None
    try:
        for el in win.GetChildren():
            ctype = getattr(el, "ControlTypeName", "")
            if ctype != "TextControl":
                continue
            name = (el.Name or "").strip()
            if not name:
                continue
            b = el.BoundingRectangle
            # in the top bar and not in the left list
            if b.top >= rect.top and b.bottom <= top_band_bottom and b.left >= left_boundary:
                # filter too-long names
                if 1 <= len(name) <= 60:
                    best = name
    except Exception:
        pass
    return best

def _names_match(a: str | None, b: str | None, exact: bool = True) -> bool:
    if not a or not b:
        return False
    if exact:
        return a.casefold().strip() == b.casefold().strip()
    return b.casefold().strip() in a.casefold().strip() or a.casefold().strip() in b.casefold().strip()

def _click_list_item_with_text(win, text: str, logs: list[str]) -> bool:
    """
    After typing into search, click the exact match in the left results list.
    """
    try:
        # Left list is usually a ListControl with ListItem children
        lst = win.ListControl(searchDepth=20)
        if not lst or not lst.Exists(0.2):
            return False
        items = lst.GetChildren()
        for it in items:
            try:
                name = (it.Name or "").strip()
                if _names_match(name, text, exact=True):
                    it.Click()
                    time.sleep(0.6)
                    _log(logs, f"Clicked search result: {name}")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

def _element_text(el) -> str:
    """
    Concatenate all descendant TextControl names. Filters timestamps/ticks heuristically.
    """
    try:
        # Fast path: sometimes the bubble has Name with full text.
        if el.Name:
            txt = el.Name.strip()
            if txt:
                return txt
    except Exception:
        pass

    texts = []
    try:
        for c in el.GetChildren():  # shallow first
            name = getattr(c, "Name", "") or ""
            ctype = getattr(c, "ControlTypeName", "")
            if ctype == "TextControl":
                t = name.strip()
                if t:
                    texts.append(t)
        # If not enough, walk a bit deeper
        if not texts:
            for c in el.GetChildren():
                for cc in c.GetChildren():
                    name = getattr(cc, "Name", "") or ""
                    ctype = getattr(cc, "ControlTypeName", "")
                    if ctype == "TextControl":
                        t = name.strip()
                        if t:
                            texts.append(t)
    except Exception:
        pass

    # Heuristic: drop pure timestamps / ticks
    import re
    cleaned = []
    for t in texts:
        if re.fullmatch(r"\d{1,2}:\d{2}\s?(AM|PM)?", t, flags=re.I):
            continue
        if t in {"Read", "Delivered"}:
            continue
        cleaned.append(t)
    return " ".join(cleaned).strip()

def _chat_split_x(win) -> int:
    """
    Rough split between left (threads) and right (chat). We assume ~280px left panel.
    If your UI layout is different, tweak this.
    """
    rect = win.BoundingRectangle
    # conservative: split 1/3 from left edge
    return rect.left + int((rect.right - rect.left) * 0.5)

def _last_incoming_message_text(win: auto.WindowControl, logs: list[str], use_ocr: bool = False) -> str | None:
    """
    Return text of the last *incoming* bubble (on the left side).
    Falls back to OCR if enabled and UIA text was empty.
    """
    try:
        pane = win.ListControl(searchDepth=10)  # chat messages list (heuristic)
    except Exception:
        pane = None

    rect = win.BoundingRectangle
    split_x = _chat_split_x(win)
    last_incoming = None

    if pane and pane.Exists(0.2):
        try:
            children = pane.GetChildren()
            # scan from bottom-most (visually last)
            for el in reversed(children):
                # candidate message containers are often Group/ListItem
                ctype = getattr(el, "ControlTypeName", "")
                if ctype not in ("GroupControl", "ListItemControl", "PaneControl"):
                    continue
                try:
                    b = el.BoundingRectangle
                except Exception:
                    continue
                cx, _ = _rect_center_xy(b)
                # incoming bubbles are on the LEFT side of the chat area
                if cx < split_x:
                    txt = _element_text(el)
                    if txt:
                        last_incoming = (el, txt)
                        break
        except Exception:
            pass

    # As a generic fallback, try scanning any visible TextControls to the left of split
    if not last_incoming:
        try:
            texts = []
            for el in win.GetChildren():
                ctype = getattr(el, "ControlTypeName", "")
                if ctype == "TextControl":
                    b = el.BoundingRectangle
                    cx, _ = _rect_center_xy(b)
                    if cx < split_x:
                        name = (el.Name or "").strip()
                        if name:
                            texts.append((el, name))
            if texts:
                last_incoming = texts[-1]
        except Exception:
            pass

    if last_incoming:
        el, ui_text = last_incoming
        if ui_text:
            return ui_text

        # OCR fallback if enabled and text empty
        if use_ocr and ImageGrab and pytesseract:
            try:
                b = el.BoundingRectangle
                # tighten bbox a bit
                pad = 4
                bbox = (max(b.left + pad, rect.left),
                        max(b.top + pad, rect.top),
                        min(b.right - pad, rect.right),
                        min(b.bottom - pad, rect.bottom))
                img = ImageGrab.grab(bbox=bbox)
                txt = pytesseract.image_to_string(img, lang="eng").strip()
                if txt:
                    _log(logs, "OCR used for incoming bubble")
                    return txt
            except Exception as e:
                _log(logs, f"OCR failed: {e}")

    return None
