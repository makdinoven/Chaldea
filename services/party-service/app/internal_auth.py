"""Internal service-to-service authentication for party-service (FEAT-169 M1).

Both directions live here, in a leaf module that imports nothing from the
service itself, so that `main.py` **and** `crud.py` can use it without the
circular import that would arise from `crud` importing `main`.

Incoming: `verify_internal_token` — a verbatim copy of the canonical
fail-closed check (`character-service/app/auth_http.py`, FEAT-162 §3.4).
Outgoing: `internal_token_headers` — headers for calls this service makes.
"""

import os
from typing import Optional

from fastapi import Header, HTTPException, status

# Read at import time into a module-level constant — tests monkeypatch this
# attribute (`monkeypatch.setattr(internal_auth, "INTERNAL_SERVICE_TOKEN", ...)`),
# the FEAT-162/167 precedent.
INTERNAL_SERVICE_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")


def verify_internal_token(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> None:
    """Reject the request unless `X-Internal-Token` matches
    `INTERNAL_SERVICE_TOKEN` from env. Empty env -> always reject.
    """
    if not INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal service token не настроен",
        )
    if not x_internal_token or x_internal_token != INTERNAL_SERVICE_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный internal token",
        )


def internal_token_headers() -> dict:
    """Headers for outgoing internal service-to-service calls (FEAT-167 §3.2.5).

    The token is read from env at call time (not import time) so tests can set
    it without reloading the module.
    """
    return {"X-Internal-Token": os.environ.get("INTERNAL_SERVICE_TOKEN", "")}
