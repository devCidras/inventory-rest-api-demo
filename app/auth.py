"""Simple API-key authentication.

Not OAuth/JWT-grade, but the level of auth that fits a small internal API:
a single shared secret sent in the `X-API-Key` header. Swapping this for
JWT/OAuth2 (e.g. per-client keys, expiry, scopes) is a straightforward
extension of this same dependency.
"""

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY = os.getenv("API_KEY", "demo-key-123")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(_api_key_header)) -> str:
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key (send it in the X-API-Key header)",
        )
    return key
