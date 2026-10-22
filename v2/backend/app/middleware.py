"""Security headers and a request-body size cap."""
from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"SAMEORIGIN",              # payslip PDFs are previewed in a same-origin iframe
    b"referrer-policy": b"no-referrer",
    b"content-security-policy": b"frame-ancestors 'self'",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
}
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware:
    """Adds hardening headers to every API response. Payroll data is never cached by default."""
    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app, self.hsts = app, hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(msg: Message) -> None:
            if msg["type"] == "http.response.start":
                headers = [(k, v) for k, v in msg.get("headers", [])]
                present = {k.lower() for k, _ in headers}
                for k, v in _HEADERS.items():
                    if k not in present:
                        headers.append((k, v))
                if b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                if self.hsts and _HSTS[0] not in present:
                    headers.append(_HSTS)
                msg = {**msg, "headers": headers}
            await send(msg)
        await self.app(scope, receive, send_wrapper)


class BodyLimitMiddleware:
    """Rejects bodies over `max_bytes` with 413: by Content-Length up front, and by counting streamed bytes.

    When the stream limit is hit the app is told the client disconnected (so it stops reading) and whatever it
    tries to answer is replaced by a 413 -- FastAPI would otherwise turn a body-read error into a 400."""
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app, self.max = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max:
            return await self._reject(send)
        total, exceeded, answered = 0, False, False

        async def limited_receive() -> Message:
            nonlocal total, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg["type"] == "http.request":
                total += len(msg.get("body", b""))
                if total > self.max:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return msg

        async def guarded_send(msg: Message) -> None:
            nonlocal answered
            if exceeded:
                if not answered:
                    answered = True
                    await self._reject(send)
                return
            await send(msg)

        await self.app(scope, limited_receive, guarded_send)
        if exceeded and not answered:
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps({"error": {"code": "payload_too_large", "message": f"Request body exceeds the {self.max // 1024} KB limit"}}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
