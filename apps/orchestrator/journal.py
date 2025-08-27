import json, time, uuid
from pathlib import Path
from typing import Any, Dict, List

_JOURNAL_DIR = Path("data/journal")
_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

def _file(op_id: str) -> Path:
    return _JOURNAL_DIR / f"{op_id}.jsonl"

def begin(operation: str, meta: Dict[str, Any]) -> str:
    op_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    append(op_id, "begin", {"operation": operation, "meta": meta})
    return op_id

def append(op_id: str, event: str, payload: Dict[str, Any]):
    with _file(op_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "event": event, **payload}) + "\n")

def read(op_id: str) -> List[Dict[str, Any]]:
    with _file(op_id).open("r", encoding="utf-8") as f:
        return [json.loads(l) for l in f]

def journaled_move(op_id: str, src: Path, dst: Path, dry_run: bool = False):
    append(op_id, "move.planned", {"src": str(src), "dst": str(dst)})
    if dry_run:
        append(op_id, "move.skipped", {"reason": "dry_run"})
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    append(op_id, "move.done", {"src": str(src), "dst": str(dst)})

def undo(op_id: str, dry_run: bool = False) -> List[str]:
    """Reverse recorded file moves in reverse order."""
    events = read(op_id)
    moves = [e for e in events if e.get("event") == "move.done"]
    actions = []
    for m in reversed(moves):
        src_now = Path(m["dst"])
        dst_back = Path(m["src"])
        if not src_now.exists():
            actions.append(f"skip missing {src_now}")
            continue
        actions.append(f"revert {src_now} -> {dst_back}")
        if not dry_run:
            dst_back.parent.mkdir(parents=True, exist_ok=True)
            src_now.rename(dst_back)
    append(op_id, "undo.done", {"count": len(moves), "dry_run": dry_run})
    return actions
