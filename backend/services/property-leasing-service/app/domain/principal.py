from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class Principal:
    subject_id: UUID
    account_type: str
    scopes: frozenset[str]
    claims: dict
    staff_id: UUID | None = None
    customer_status: str | None = None
    role: str | None = None

    def has(self, permission: str) -> bool:
        return permission in self.scopes

    @property
    def is_admin(self) -> bool:
        return self.role == "manager_admin" or any(scope.endswith("_all") for scope in self.scopes)
