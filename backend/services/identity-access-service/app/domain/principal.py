from dataclasses import dataclass

from safescan_common.auth import Principal as CommonPrincipal


@dataclass(frozen=True)
class Principal(CommonPrincipal):
    """Identity-owned extension with database identifiers never put into JWTs."""

    user_id: int | None = None
    session_internal_id: int | None = None
