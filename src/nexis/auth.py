"""Firebase Auth middleware for FastAPI."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import auth as firebase_auth  # type: ignore[import-untyped]
from firebase_admin import credentials  # type: ignore[import-untyped]
from firebase_admin.auth import (  # type: ignore[import-untyped]
    CertificateFetchError,
    ExpiredIdTokenError,
    InvalidIdTokenError,
    RevokedIdTokenError,
    UserDisabledError,
)
from fastapi import HTTPException, Request


_firebase_initialized = False

_401 = dict(status_code=401, headers={"WWW-Authenticate": "Bearer"})


def _init_firebase() -> None:
    global _firebase_initialized
    if _firebase_initialized:
        return
    try:
        firebase_admin.get_app()
    except ValueError:
        # App not yet initialised — create it now.
        project_id = os.environ.get("GCP_PROJECT_ID")
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred, {"projectId": project_id})
    _firebase_initialized = True


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
        raise HTTPException(detail="Missing or invalid Authorization header", **_401)

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(detail="Empty bearer token", **_401)

    _init_firebase()

    try:
        decoded = await asyncio.to_thread(firebase_auth.verify_id_token, token)
    except (
        InvalidIdTokenError,
        ExpiredIdTokenError,
        RevokedIdTokenError,
        UserDisabledError,
        CertificateFetchError,
    ) as exc:
        raise HTTPException(detail="Invalid or expired token", **_401) from exc

    return CurrentUser(uid=decoded["uid"], email=decoded.get("email"))
