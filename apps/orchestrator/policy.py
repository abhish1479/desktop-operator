import time, re, yaml
from pathlib import Path

CFG_PATH = Path(__file__).resolve().parents[2] / "config" / "guardrails.yaml"

class Guardrails:
    def __init__(self):
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        self._whitelist = [re.compile(p) for p in (cfg.get("terminal",{}).get("whitelist") or [])]
        self._denylist = [re.compile(d) for d in (cfg.get("terminal",{}).get("denylist") or [])]
        self._max_steps = cfg.get("limits",{}).get("max_steps", 40)
        self._max_minutes = cfg.get("limits",{}).get("max_minutes", 20)
        self._start = time.time()

    def validate_terminal(self, cmd: str):
        for d in self._denylist:
            if d.search(cmd):
                raise ValueError(f"Command denied by policy: {cmd}")
        if not any(w.search(cmd) for w in self._whitelist):
            raise ValueError(f"Command not in whitelist: {cmd}")

    def max_steps(self) -> int:
        return self._max_steps

    def time_budget_exceeded(self) -> bool:
        return (time.time() - self._start) > (self._max_minutes * 60)
