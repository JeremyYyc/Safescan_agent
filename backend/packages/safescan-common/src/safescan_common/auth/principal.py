from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Principal:
    subject: str
    scopes: frozenset[str]
    claims: dict[str, Any]
    session_id: str | None = None
    account_type: str | None = None

    def has(self, permission: str) -> bool:
        return permission in self.scopes

    def has_all(self, permissions: set[str] | frozenset[str]) -> bool:
        return permissions.issubset(self.scopes)
