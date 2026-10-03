"""Small helpers shared by the test modules (importable without side effects)."""
import asyncio
import base64
import json

import itsdangerous

OWNER = "owner@example.com"
TEST_API_KEY = "test-anthropic-key"


def run(coro):
    """Run a coroutine to completion (the suite has no async test plugin)."""
    return asyncio.run(coro)


def make_session_cookie(email: str) -> str:
    """A validly signed session cookie, as the app itself would issue."""
    from backend.config import settings

    signer = itsdangerous.TimestampSigner(settings.SECRET_KEY)
    payload = base64.b64encode(json.dumps({"email": email}).encode("utf-8"))
    return signer.sign(payload).decode("utf-8")
