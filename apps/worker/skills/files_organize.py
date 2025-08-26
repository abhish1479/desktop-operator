import os, re, shutil
from dataclasses import dataclass

@dataclass
class Rule:
    when_ext: list[str] | None = None
    when_regex: str | None = None
    action: str = "move"  # move|delete|zip
    to: str | None = None

def run(root: str, rules: list[dict], dry_run: bool = True) -> dict:
    if not os.path.isdir(root):
        return {"ok": False, "error": f"not_a_dir: {root}"}
    applied = []
    for fname in os.listdir(root):
        fpath = os.path.join(root, fname)
        if not os.path.isfile(fpath): 
            continue
        for r in rules:
            rule = Rule(**r)
            if rule.when_ext and not any(fname.lower().endswith(e) for e in rule.when_ext):
                continue
            if rule.when_regex and not re.search(rule.when_regex, fname, re.I):
                continue
            if rule.action == "move" and rule.to:
                dest_dir = os.path.join(root, rule.to)
                os.makedirs(dest_dir, exist_ok=True)
                if not dry_run:
                    shutil.move(fpath, os.path.join(dest_dir, fname))
                applied.append({"file": fname, "action": "move", "to": rule.to})
            elif rule.action == "delete":
                if not dry_run:
                    os.remove(fpath)
                applied.append({"file": fname, "action": "delete"})
            break
    return {"ok": True, "dry_run": dry_run, "applied": applied}
