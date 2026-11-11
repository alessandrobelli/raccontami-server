"""Run from the repository root with:  python -m unittest discover tests"""

import asyncio
import unittest

from raccontami_sync.gate import Gate


class Inner:
    """Stands in for the server: reads the whole body, then answers 200."""

    def __init__(self):
        self.reached = False
        self.received = 0

    async def __call__(self, scope, receive, send):
        self.reached = True
        while True:
            message = await receive()
            self.received += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def call(path="/v1/jobs", token="secret", length=None, chunks=(b"",)):
    """Sends one request through the gate; returns (status, the inner app)."""
    inner = Inner()
    gate = Gate(inner, token="secret", open_paths=("/v1/hello",), default_limit=100, limits={"/v1/jobs": 1000})
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode("latin-1")))
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    pending = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    sent = []

    async def receive():
        return pending.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(gate({"type": "http", "path": path, "headers": headers}, receive, send))
    return sent[0]["status"], inner


class GateTest(unittest.TestCase):
    def test_the_right_token_reaches_the_server(self):
        self.assertEqual(200, call()[0])

    def test_without_a_token_the_answer_is_401(self):
        self.assertEqual(401, call(token=None)[0])

    def test_without_a_token_the_body_is_never_read(self):
        self.assertFalse(call(token=None, chunks=(b"x" * 50,))[1].reached)

    def test_a_wrong_token_is_401(self):
        self.assertEqual(401, call(token="other")[0])

    def test_a_token_with_odd_characters_is_401_not_an_error(self):
        self.assertEqual(401, call(token="sécret")[0])

    def test_the_open_path_needs_no_token(self):
        self.assertEqual(200, call(path="/v1/hello", token=None)[0])

    def test_a_declared_size_over_the_limit_is_413(self):
        self.assertEqual(413, call(length=1001)[0])

    def test_a_declared_size_over_the_limit_is_refused_before_the_body(self):
        self.assertFalse(call(length=1001)[1].reached)

    def test_a_body_without_a_declared_size_is_cut_off_at_the_limit(self):
        self.assertEqual(413, call(chunks=(b"x" * 600, b"x" * 600))[0])

    def test_other_paths_use_the_default_limit(self):
        self.assertEqual(413, call(path="/v1/narrations", length=101)[0])

    def test_a_size_that_is_not_a_number_is_413(self):
        self.assertEqual(413, call(length="lots")[0])


if __name__ == "__main__":
    unittest.main()
