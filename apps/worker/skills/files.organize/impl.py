from pathlib import Path
from typing import List, Dict
from apps.orchestrator.policy import policy
from apps.orchestrator.journal import begin, journaled_move
import fnmatch, os

def run(payload: Dict):
    root = Path(payload["root"]).expanduser().resolve()
    dry_run = bool(payload.get("dry_run", True))
    rules: List[Dict] = payload["rules"]

    # Sandbox check
    ok, reason = policy.sandbox_guard(str(root))
    if not ok:
        raise PermissionError(reason)

    op_id = begin("files.organize", {"root": str(root), "dry_run": dry_run})

    affected = 0
    for rule in rules:
        action = rule["action"]
        to = rule.get("to")
        exts = [e.lower() for e in rule.get("when_ext", [])]
        glob = rule.get("when_glob")

        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if exts and p.suffix.lower() not in exts:
                continue
            if glob and not fnmatch.fnmatch(p.name, glob):
                continue

            if action in ("move", "copy"):
                if not to:
                    continue
                dst = (root / to / p.name).resolve()
                policy_ok, reason = policy.sandbox_guard(str(dst))
                if not policy_ok:
                    raise PermissionError(reason)
                journaled_move(op_id, p, dst, dry_run=dry_run)
                affected += 1
            elif action == "delete":
                if dry_run:
                    affected += 1
                else:
                    # delete needs explicit approval (guarded upstream)
                    p.unlink(missing_ok=True)
                    affected += 1

    return {"op_id": op_id, "affected": affected, "dry_run": dry_run}
