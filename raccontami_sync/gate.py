"""Checks a request before any of its body is read.

FastAPI reads the whole body (an audiobook upload, or the text of a book) before it
runs a route's dependencies, so a token check done there comes only after the last
byte: anyone who could reach the port could fill the disk or the memory without a
token. This sits in front and answers first:

  401  the token is missing or wrong (every path except the open ones)
  413  the body is larger than the path allows, by its Content-Length or, for a body
       sent without one, as soon as more than that has arrived
"""

from __future__ import annotations

import json
import secrets


class _TooLarge(Exception):
    pass


async def _reply(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class Gate:
    """ASGI middleware. [open_paths] need no token; [limits] maps a path to its largest
    body in bytes, any other path gets [default_limit]."""

    def __init__(self, app, token: str, open_paths: tuple[str, ...], default_limit: int, limits: dict[str, int]):
        self.app = app
        self.expected = f"Bearer {token}".encode()
        self.open_paths = open_paths
        self.default_limit = default_limit
        self.limits = limits

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in self.open_paths:
            await self.app(scope, receive, send)
            return
        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        # bytes, so a header with odd characters is simply a wrong token, not an error
        if not secrets.compare_digest(headers.get(b"authorization", b""), self.expected):
            await _reply(send, 401, "bad token")
            return
        limit = self.limits.get(scope["path"], self.default_limit)
        declared = headers.get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await _reply(send, 413, "too large")
            return

        seen = 0
        started = False

        async def counted():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _TooLarge()
            return message

        async def watched(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, watched)
        except _TooLarge:
            if not started:
                await _reply(send, 413, "too large")
