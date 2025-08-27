# apps/orchestrator/llm_traced.py
from __future__ import annotations
import time, traceback
from typing import Any

class TracedLLM:
    def __init__(self, inner_llm):
        self.inner = inner_llm
        self.trace: list[dict[str, Any]] = []

    def _log(self, evt: str, **data):
        self.trace.append({"ts": time.time(), "evt": evt, **data})

    # ---- same API as your LLM ----
    def bootstrap(self, goal: str, dry_run: bool, budget_rupees: int | None):
        self._log("llm.bootstrap.begin", goal=goal, dry_run=dry_run, budget_rupees=budget_rupees)
        try:
            msgs = self.inner.bootstrap(goal, dry_run, budget_rupees)
            # Record just the tail to avoid huge payloads
            self._log("llm.bootstrap.end", ok=True, last_msg=msgs[-1] if msgs else None, msg_count=len(msgs or []))
            return msgs
        except Exception as e:
            self._log("llm.bootstrap.error", ok=False, error=str(e), tb=traceback.format_exc())
            raise

    def next_tool_call(self, messages: list[dict]):
        self._log("llm.next.begin", last_user=next((m for m in reversed(messages) if m.get("role") in {"user","system"}), None))
        try:
            call = self.inner.next_tool_call(messages)
            # Capture raw text if your inner LLM exposes it (optional)
            raw = getattr(self.inner, "last_raw", None)
            self._log("llm.next.end", ok=True, call=call, last_raw=raw)
            return call
        except Exception as e:
            self._log("llm.next.error", ok=False, error=str(e), tb=traceback.format_exc())
            raise

    def observe(self, messages: list[dict], tool_name: str, args: dict, obs: dict):
        self._log("llm.observe", tool=tool_name, args=args, obs=obs)
        try:
            out = self.inner.observe(messages, tool_name, args, obs)
            return out
        except Exception as e:
            self._log("llm.observe.error", ok=False, error=str(e), tb=traceback.format_exc())
            raise

    # optional: expose trace so the runner can include it in results/stream
    def dump_trace(self) -> list[dict]:
        return list(self.trace)
