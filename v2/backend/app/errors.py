"""Structured error envelope: {"error": {"code", "message", "details"?}} -- no stack traces, no paths."""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("pv2")
_CODES = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict",
          413: "payload_too_large", 422: "validation_error", 429: "rate_limited"}


def _body(status: int, message: str, details=None) -> dict:
    err = {"code": _CODES.get(status, "error"), "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        return JSONResponse(_body(exc.status_code, str(exc.detail)), status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body(422, "Request validation failed", details), status_code=422)

    @app.exception_handler(Exception)
    async def _any(_: Request, exc: Exception):
        log.exception("unhandled error")  # logged server-side without request bodies
        return JSONResponse(_body(500, "Internal server error"), status_code=500)
