from __future__ import annotations

import os
import logging
import secrets
import json
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "whalasahib@gmail.com")
APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"

SESSION_COOKIE = "agentx_session"
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-in-production")

# ── 5-Tester Access Codes ──────────────────────────────────────────────────
# Each code: {"code": str, "label": str, "claimed": bool, "claimed_by": str}
ACCESS_CODES_FILE = Path(__file__).resolve().parent / ".access_codes.json"


def _load_access_codes() -> list[dict]:
    if ACCESS_CODES_FILE.exists():
        try:
            return json.loads(ACCESS_CODES_FILE.read_text())
        except Exception:
            pass
    return []


def _save_access_codes(codes: list[dict]):
    ACCESS_CODES_FILE.write_text(json.dumps(codes, indent=2))


def generate_access_codes(count: int = 5) -> list[dict]:
    """Generate N unique random access codes for testers."""
    codes = []
    for i in range(count):
        codes.append({
            "code": secrets.token_hex(8),  # 16-char hex code
            "label": f"Tester {i + 1}",
            "claimed": False,
            "claimed_by": "",
        })
    _save_access_codes(codes)
    return codes


def validate_access_code(code: str) -> dict | None:
    """Check if an access code is valid and unclaimed. Returns the code data or None."""
    codes = _load_access_codes()
    for c in codes:
        if c["code"] == code:
            if c["claimed"]:
                return None  # Already used
            return c
    return None


def claim_access_code(code: str, claimer: str) -> bool:
    """Mark an access code as claimed. Returns True if successful."""
    codes = _load_access_codes()
    for c in codes:
        if c["code"] == code and not c["claimed"]:
            c["claimed"] = True
            c["claimed_by"] = claimer
            _save_access_codes(codes)
            return True
    return False


def list_access_codes() -> list[dict]:
    """Return all access codes (for admin display)."""
    return _load_access_codes()


# ── Auth helpers ────────────────────────────────────────────────────────


def is_google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def get_google_auth_url(state: str = "oauth_state") -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{APP_URL}/api/auth/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{AUTH_URI}?{urlencode(params)}"


async def exchange_code(code: str) -> dict | None:
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": f"{APP_URL}/api/auth/callback",
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(TOKEN_URI, data=data)
            if resp.status_code != 200:
                logger.warning("Token exchange failed: %s", resp.text)
                return None
            tokens = resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return None
            headers = {"Authorization": f"Bearer {access_token}"}
            user_resp = await client.get(USERINFO_URI, headers=headers)
            if user_resp.status_code == 200:
                return user_resp.json()
    except Exception as e:
        logger.error("OAuth error: %s", e)
    return None


def _is_authenticated(request: Request) -> bool:
    session = request.cookies.get(SESSION_COOKIE)
    if not session:
        return False
    return bool(session)  # any non-empty session counts


async def require_auth(request: Request):
    """FastAPI dependency — auth is DISABLED in dev mode. Always returns True."""
    return True


async def optional_auth(request: Request) -> bool:
    """Returns True if authenticated, False otherwise. No exception."""
    return _is_authenticated(request)
