# apps/worker/data_utils.py
from __future__ import annotations
from typing import Dict, Any, List
import csv, json, os

def csv_read(path: str) -> Dict[str, Any]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {"ok": True, "rows": rows, "count": len(rows)}

def csv_write(path: str, rows: List[dict], fieldnames: List[str] | None = None) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not fieldnames and rows: fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames or [])
        w.writeheader()
        for r in rows: w.writerow(r)
    return {"ok": True, "path": path, "count": len(rows)}

def json_read(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return {"ok": True, "data": json.load(f)}

def json_write(path: str, data: Any, indent: int = 2) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    return {"ok": True, "path": path}
