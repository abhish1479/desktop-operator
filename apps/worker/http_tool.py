# apps/worker/http_tool.py
from __future__ import annotations
from typing import Dict, Any, Optional
import requests

def http_request(method: str, url: str, headers: Optional[dict] = None,
                 params: Optional[dict] = None, json: Any = None, data: Any = None,
                 timeout_sec: int = 30) -> Dict[str, Any]:
    r = requests.request(method.upper(), url, headers=headers, params=params, json=json, data=data, timeout=timeout_sec)
    return {
        "ok": r.ok, "status": r.status_code, "headers": dict(r.headers),
        "text": r.text[:100000],  # cap
        "url": r.url,
    }
