from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.auth_jwt import bootstrap_user, login_user

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(body: RegisterRequest) -> dict:
    try:
        return bootstrap_user(body.email, body.password)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login")
def login(body: LoginRequest) -> dict:
    try:
        return login_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
