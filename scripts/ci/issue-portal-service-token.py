#!/usr/bin/env python3
"""Issue a short-lived CI service token from the migrated client allowlist."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time


def encode(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: issue-portal-service-token.py CLIENT_CODE")
    secret = os.environ["AUTH_SECRET"].encode()
    now = int(time.time())
    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = encode(
        {
            "aud": os.getenv("IDENTITY_INTERNAL_AUDIENCE", "safescan-identity-internal"),
            "exp": now + 300,
            "iat": now,
            "iss": os.getenv("AUTH_ISSUER", "safescan-identity"),
            "jti": secrets.token_hex(16),
            "nbf": now,
            "scopes": json.loads(os.environ["PORTAL_SERVICE_SCOPES"]),
            "sub": f"service:{sys.argv[1]}",
        }
    )
    signing_input = f"{header}.{payload}"
    signature = base64.urlsafe_b64encode(
        hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    ).rstrip(b"=")
    print(f"{signing_input}.{signature.decode()}")


if __name__ == "__main__":
    main()
