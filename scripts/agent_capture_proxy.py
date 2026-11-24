"""Record the model requests of a real agent run, for scripts/agent_replay.py.

Sits between llama-mcp-router and llama-server and passes everything through unchanged, except that it appends every
POST .../chat/completions body to <out>.jsonl (and the llama-server timings of its answer to <out>.timings.jsonl) and can
give requests without a reasoning effort one (--effort), e.g. to record an agent at xhigh/max when its client sends none.

    .venv/bin/python scripts/agent_capture_proxy.py --backend http://127.0.0.1:8081 --port 8098 --out results/speed/agent/trace
    # then a second router with --backend http://127.0.0.1:8098 runs the agent task (see reports/inkling2mini/AGENT-SPEED.md)

Needs starlette, httpx and uvicorn (llmapi_server's venv has them).
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from typing import Any, AsyncIterator, Dict, Optional

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization", "proxy-authenticate",
       "content-length", "content-encoding", "host"}


def build_app(backend: str, out: str, effort: Optional[str]) -> Starlette:
    client = httpx.AsyncClient(base_url=backend.rstrip("/"), timeout=httpx.Timeout(None, connect=10.0))
    lock = threading.Lock()
    state = {"n": 0}

    def append(path: str, rec: Dict[str, Any]) -> None:
        with lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    async def proxy(request: Request) -> Response:
        path = "/" + request.path_params["path"]
        url = path + (("?" + request.url.query) if request.url.query else "")
        body = await request.body()
        idx = None
        if request.method == "POST" and path.endswith("chat/completions") and body:
            try:
                data = json.loads(body)
            except ValueError:
                data = None
            if isinstance(data, dict):
                if effort and "reasoning_effort" not in data and "reasoning_effort" not in (data.get("chat_template_kwargs") or {}):
                    data["reasoning_effort"] = effort
                    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                with lock:
                    state["n"] += 1
                    idx = state["n"]
                append(out + ".jsonl", {"i": idx, "t": round(time.time(), 3), "path": path,
                                        "conversation": request.headers.get("x-conversation-id"), "body": data})
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
        headers["accept-encoding"] = "identity"
        t0 = time.time()
        r = await client.send(client.build_request(request.method, url, content=body, headers=headers), stream=True)
        out_headers = {k: v for k, v in r.headers.items() if k.lower() not in HOP}

        async def relay() -> AsyncIterator[bytes]:
            buf, last, finish = b"", None, None
            try:
                async for piece in r.aiter_raw():
                    yield piece
                    if idx is None:
                        continue
                    buf += piece
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line.startswith(b"data: {"):
                            try:
                                d = json.loads(line[6:])
                            except ValueError:
                                continue
                            if isinstance(d.get("timings"), dict):
                                last = d["timings"]
                            fr = ((d.get("choices") or [{}])[0] or {}).get("finish_reason")
                            finish = fr or finish
                if idx is not None and last is None and buf.strip().startswith(b"{"):
                    try:  # non-streaming answer
                        d = json.loads(buf)
                        last = d.get("timings")
                        finish = ((d.get("choices") or [{}])[0] or {}).get("finish_reason")
                    except ValueError:
                        pass
            finally:
                await r.aclose()
                if idx is not None:
                    append(out + ".timings.jsonl", {"i": idx, "status": r.status_code, "wall_s": round(time.time() - t0, 3),
                                                    "finish_reason": finish, "timings": last})

        return StreamingResponse(relay(), status_code=r.status_code, headers=out_headers)

    return Starlette(routes=[Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend", default="http://127.0.0.1:8081")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8098)
    ap.add_argument("--out", required=True, help="path prefix: <out>.jsonl (requests) and <out>.timings.jsonl")
    ap.add_argument("--effort", default=None, help="reasoning_effort for requests that set none (e.g. max = xhigh = 0.99)")
    a = ap.parse_args()
    uvicorn.run(build_app(a.backend, a.out, a.effort), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
