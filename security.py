from __future__ import annotations

import os
from functools import wraps

import jwt
import requests
from flask import abort, flash, g, redirect, request, session, url_for
from jwt import PyJWKClient

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
JWT_ISSUER = f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else ""
JWKS_URL = f"{JWT_ISSUER}/.well-known/jwks.json" if JWT_ISSUER else ""
_jwks_client = None


class AuthenticationUnavailable(Exception):
    pass


def _config_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY)


def sign_in_with_password(email: str, password: str) -> dict:
    if not _config_ready():
        raise AuthenticationUnavailable("Employee sign-in has not been configured.")
    response = requests.post(
        f"{SUPABASE_URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=12,
    )
    if response.status_code in (400, 401):
        raise ValueError("Email or password is incorrect, or the invitation has not been accepted.")
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise AuthenticationUnavailable("The identity provider did not return a session.")
    claims = verify_access_token(token)
    profile = get_employee_profile(claims["sub"])
    if not profile or not profile.get("is_active"):
        raise ValueError("This account has not been approved for employee access. Contact the system administrator.")
    return {"token": token, "profile": profile, "expires_in": payload.get("expires_in", 3600)}


def verify_access_token(token: str) -> dict:
    global _jwks_client
    if not _config_ready():
        raise AuthenticationUnavailable("Employee sign-in has not been configured.")
    try:
        if _jwks_client is None:
            _jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            leeway=5,
        )
    except jwt.PyJWTError as exc:
        raise ValueError("Your session is invalid or has expired. Please sign in again.") from exc
    except requests.RequestException as exc:
        raise AuthenticationUnavailable("Could not verify your session with Supabase Auth.") from exc


def get_employee_profile(user_id: str) -> dict | None:
    if not _config_ready():
        raise AuthenticationUnavailable("Employee sign-in has not been configured.")
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/employee_profiles",
        params={
            "select": "user_id,email,full_name,role,is_active",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        },
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        },
        timeout=12,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def current_employee() -> dict | None:
    if "employee" in g:
        return g.employee
    g.employee = None
    token = session.get("supabase_access_token")
    if not token:
        return None
    try:
        claims = verify_access_token(token)
        profile = get_employee_profile(claims["sub"])
        if profile and profile.get("is_active"):
            g.employee = profile
        else:
            session.clear()
    except (ValueError, AuthenticationUnavailable, requests.RequestException):
        session.clear()
    return g.employee


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_employee() is None:
            return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*allowed_roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            employee = current_employee()
            if employee["role"] not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate
