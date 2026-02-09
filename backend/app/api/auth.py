from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import create_token, require_user
from app.db import create_user, get_user_by_email, get_user_by_id, update_username, verify_user

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class ProfileUpdateRequest(BaseModel):
    username: str


def _safe_user_payload(user: dict) -> dict:
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "username": user.get("username"),
        "storage_uuid": user.get("storage_uuid"),
        "avatar": user.get("avatar"),
        "create_time": user.get("create_time"),
        "update_time": user.get("update_time"),
    }


@router.post("/auth/login")
def login(payload: LoginRequest) -> JSONResponse:
    email = payload.email.strip().lower()
    user = verify_user(email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user)
    return JSONResponse(jsonable_encoder({"token": token, "user": _safe_user_payload(user)}))


@router.post("/auth/register")
def register(payload: RegisterRequest) -> JSONResponse:
    email = payload.email.strip().lower()
    username = payload.username.strip()
    if get_user_by_email(email):
        raise HTTPException(status_code=409, detail="Email already exists")
    user = create_user(email, username, payload.password)
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")
    token = create_token(user)
    return JSONResponse(jsonable_encoder({"token": token, "user": _safe_user_payload(user)}))


@router.put("/auth/profile")
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: dict = Depends(require_user),
) -> JSONResponse:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not update_username(int(current_user["user_id"]), username):
        raise HTTPException(status_code=500, detail="Failed to update profile")
    user = get_user_by_id(int(current_user["user_id"]))
    if not user:
        raise HTTPException(status_code=500, detail="Failed to load profile")
    token = create_token(user)
    return JSONResponse(jsonable_encoder({"token": token, "user": _safe_user_payload(user)}))
