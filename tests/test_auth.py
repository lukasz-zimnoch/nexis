"""Tests for Firebase Auth middleware."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexis.auth import CurrentUser, get_current_user

# ---------------------------------------------------------------------------
# Minimal app for testing the dependency
# ---------------------------------------------------------------------------

_test_app = FastAPI()


@_test_app.get("/protected")
async def protected_endpoint(user: CurrentUser = __import__("fastapi").Depends(get_current_user)):
    return {"uid": user.uid, "email": user.email}


client = TestClient(_test_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_auth_header_returns_401():
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_non_bearer_header_returns_401():
    resp = client.get("/protected", headers={"Authorization": "Basic abc123"})
    assert resp.status_code == 401


def test_empty_bearer_token_returns_401():
    resp = client.get("/protected", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401


def test_invalid_token_returns_401():
    with (
        patch("nexis.auth._firebase_initialized", True),
        patch("nexis.auth.firebase_auth") as mock_fb,
    ):
        mock_fb.verify_id_token.side_effect = Exception("invalid token")
        resp = client.get("/protected", headers=_auth_header("bad-token"))
    assert resp.status_code == 401


def test_valid_token_returns_current_user():
    decoded = {"uid": "user-123", "email": "user@example.com"}
    with (
        patch("nexis.auth._firebase_initialized", True),
        patch("nexis.auth.firebase_auth") as mock_fb,
    ):
        mock_fb.verify_id_token.return_value = decoded
        resp = client.get("/protected", headers=_auth_header("valid-token"))

    assert resp.status_code == 200
    data = resp.json()
    assert data["uid"] == "user-123"
    assert data["email"] == "user@example.com"


def test_valid_token_without_email():
    decoded = {"uid": "user-456"}
    with (
        patch("nexis.auth._firebase_initialized", True),
        patch("nexis.auth.firebase_auth") as mock_fb,
    ):
        mock_fb.verify_id_token.return_value = decoded
        resp = client.get("/protected", headers=_auth_header("valid-token"))

    assert resp.status_code == 200
    assert resp.json()["email"] is None
