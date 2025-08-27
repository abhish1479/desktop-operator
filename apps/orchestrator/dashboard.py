from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter(prefix="/dashboard")

@router.get("/recent")
def recent(limit: int = 20):
    jdir = Path("data/journal")
    items = []
    for p in sorted(jdir.glob("*.jsonl"), reverse=True)[:limit]:
        with p.open("r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f]
        begin = next((l for l in lines if l["event"] == "begin"), None)
        items.append({"op_id": p.stem, "begin": begin})
    return {"items": items}
