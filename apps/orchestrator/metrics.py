from fastapi import APIRouter, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

router = APIRouter()

REQUESTS_TOTAL = Counter("requests_total", "Total API requests", ["path", "method", "code"])
LATENCY = Histogram("request_latency_ms", "Request latency (ms)")

@router.get("/healthz")
def healthz():
    return {"ok": True}

@router.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
