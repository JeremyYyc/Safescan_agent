from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import validate_nonblank


class UserStatusRequest(BaseModel):
    status: Literal["active", "suspended", "deleted"]
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(gt=0)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class OptionalReasonRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class StaffCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=150)
    staff_code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    role_id: UUID
    hired_at: datetime | None = None

    _nonblank = field_validator("username", "display_name")(validate_nonblank)


class StaffEmploymentRequest(BaseModel):
    employment_status: Literal["pending", "active", "on_leave", "ended"]
    effective_at: datetime
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(gt=0)


class StaffRoleRequest(BaseModel):
    role_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(gt=0)


class RolePermissionsRequest(BaseModel):
    permission_codes: list[str] = Field(max_length=500)
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(gt=0)


class RoleStatusRequest(BaseModel):
    status: Literal["active", "disabled"]
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(gt=0)


class ServiceClientCreateRequest(BaseModel):
    client_code: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    credential_ref: str = Field(min_length=1, max_length=500)
    allowed_audiences: list[str] = Field(max_length=100)
    allowed_scopes: list[str] = Field(max_length=500)
    key_id: str | None = Field(default=None, max_length=200)


class ServiceClientUpdateRequest(BaseModel):
    credential_ref: str | None = Field(default=None, min_length=1, max_length=500)
    allowed_audiences: list[str] | None = Field(default=None, max_length=100)
    allowed_scopes: list[str] | None = Field(default=None, max_length=500)
    status: Literal["active", "disabled"] | None = None
    key_id: str | None = Field(default=None, max_length=200)
    version: int = Field(gt=0)


class ServiceClientRotateRequest(BaseModel):
    credential_ref: str = Field(min_length=1, max_length=500)
    key_id: str = Field(min_length=1, max_length=200)
    version: int = Field(gt=0)
