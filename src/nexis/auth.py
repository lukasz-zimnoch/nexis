"""Firebase Auth middleware for FastAPI."""

from __future__ import annotations

import os
from dataclasses import dataclass

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]
from firebase_admin import credentials  # type: ignore[import-untyped]
from fastapi import HTTPException, Request


def _init_firebase() -> None:
    """Idempotent, thread-safe Firebase Admin SDK initialisation using ADC."""
    try:
        firebase_admin.get_app()
        return  # already initialised
    except ValueError:
        pass
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred, {"projectId": project_id})
    except ValueError:
        pass  # another thread beat us to it


@dataclass
class CurrentUser:
    uid: str
    email: str | None


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI dependency that verifies a Firebase ID token.

    Raises HTTP 401 on missing or invalid tokens.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    _init_firebase()

    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return CurrentUser(uid=decoded["uid"], email=decoded.get("email"))
