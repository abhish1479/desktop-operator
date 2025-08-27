import time, uuid, json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class JsonLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id", str(uuid.uuid4()))
        start = time.perf_counter()
        resp = await call_next(request)
        dur = (time.perf_counter() - start) * 1000
        log = {
            "ts": time.time(),
            "rid": rid,
            "path": request.url.path,
            "method": request.method,
            "status": resp.status_code,
            "duration_ms": round(dur, 2),
        }
        print(json.dumps(log), flush=True)
        resp.headers["x-request-id"] = rid
        return resp
