from pydantic import BaseModel, EmailStr, Field, field_validator


def validate_password(value: str) -> str:
    if len(value) < 12 or len(value) > 256:
        raise ValueError("password must contain between 12 and 256 characters")
    if not any(char.islower() for char in value) or not any(char.isupper() for char in value):
        raise ValueError("password must include lower and upper case characters")
    if not any(char.isdigit() for char in value):
        raise ValueError("password must include a number")
    return value


def validate_nonblank(value: str | None) -> str | None:
    if value is not None and not value.strip():
        raise ValueError("value must not be blank")
    return value


class GuestSessionRequest(BaseModel):
    device_id: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, min_length=2, max_length=20)


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=1, max_length=100)
    password: str
    guest_session_id: str | None = None
    locale: str | None = Field(default=None, min_length=2, max_length=20)
    accepted_terms_version: str = Field(min_length=1, max_length=40)

    _password = field_validator("password")(validate_password)
    _username = field_validator("username")(validate_nonblank)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    device_label: str | None = Field(default=None, max_length=200)
    remember_me: bool = False


class EmailRequest(BaseModel):
    email: EmailStr | None = None
    locale: str | None = Field(default=None, min_length=2, max_length=20)


class PasswordResetRequest(BaseModel):
    email: EmailStr
    locale: str | None = Field(default=None, min_length=2, max_length=20)


class ActionTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class ActionPasswordRequest(ActionTokenRequest):
    new_password: str
    device_label: str | None = Field(default=None, max_length=200)

    _password = field_validator("new_password")(validate_password)


class LogoutAllRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
