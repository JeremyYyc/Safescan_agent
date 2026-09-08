from dataclasses import dataclass
from typing import Any

import jwt


@dataclass(frozen=True)
class JWTVerifier:
    secret: str
    issuer: str
    audience: str
    algorithms: tuple[str, ...] = ("HS256",)
    required_claims: tuple[str, ...] = ("exp", "iat", "nbf", "iss", "aud", "sub", "jti")

    def decode(self, token: str, *, audience: str | None = None) -> dict[str, Any]:
        return jwt.decode(
            token,
            self.secret,
            algorithms=list(self.algorithms),
            audience=audience or self.audience,
            issuer=self.issuer,
            options={"require": list(self.required_claims)},
        )
