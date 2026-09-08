from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import validate_nonblank, validate_password


class ProfileUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    avatar: str | None = Field(default=None, max_length=2048)
    locale: str | None = Field(default=None, min_length=2, max_length=20)
    version: int = Field(gt=0)

    _username = field_validator("username")(validate_nonblank)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str

    _password = field_validator("new_password")(validate_password)


class AccountDeleteRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    reason: str | None = Field(default=None, max_length=500)
    version: int = Field(gt=0)
