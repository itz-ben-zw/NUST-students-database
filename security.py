from __future__ import annotations

import os
import hashlib
import secrets
from datetime import datetime, timezone
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


def create_web_session(access_token: str, user_id: str) -> str:
    opaque_id = secrets.token_urlsafe(40)
    key_hash = hashlib.sha256(opaque_id.encode("utf-8")).hexdigest()
    claims = verify_access_token(access_token)
    expires_at = datetime.fromtimestamp(claims["exp"], timezone.utc).isoformat()
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/employee_web_sessions",
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY,
                 "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"},
        json={"session_key_hash": key_hash, "user_id": user_id,
              "access_token": access_token, "expires_at": expires_at},
        timeout=12,
    )
    response.raise_for_status()
    return opaque_id


def load_web_session(opaque_id: str) -> dict | None:
    key_hash = hashlib.sha256(opaque_id.encode("utf-8")).hexdigest()
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/employee_web_sessions",
        params={"select": "user_id,access_token,expires_at",
                "session_key_hash": f"eq.{key_hash}", "limit": "1"},
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY,
                 "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
        timeout=12,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def delete_web_session(opaque_id: str | None) -> None:
    if not opaque_id or not _config_ready():
        return
    key_hash = hashlib.sha256(opaque_id.encode("utf-8")).hexdigest()
    response = requests.delete(
        f"{SUPABASE_URL}/rest/v1/employee_web_sessions",
        params={"session_key_hash": f"eq.{key_hash}"},
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY,
                 "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
        timeout=12,
    )
    response.raise_for_status()


def current_employee() -> dict | None:
    if "employee" in g:
        return g.employee
    g.employee = None
    opaque_id = session.get("web_session_id")
    if not opaque_id:
        return None
    try:
        stored = load_web_session(opaque_id)
        if not stored:
            session.clear()
            return None
        claims = verify_access_token(stored["access_token"])
        profile = get_employee_profile(claims["sub"])
        if profile and profile.get("is_active") and profile["user_id"] == stored["user_id"]:
            g.employee = profile
        else:
            delete_web_session(opaque_id)
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


def list_employee_profiles() -> list[dict]:
    if not _config_ready():
        raise AuthenticationUnavailable("Employee management has not been configured.")
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/employee_profiles",
        params={"select": "user_id,email,full_name,role,is_active,created_at", "order": "created_at.desc"},
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY,
                 "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
        timeout=12,
    )
    response.raise_for_status()
    return response.json()


def invite_employee(email: str, full_name: str, role: str, invited_by: str) -> None:
    if not _config_ready():
        raise AuthenticationUnavailable("Employee management has not been configured.")
    allowed_roles = {"system_admin", "finance", "student_records", "auditor"}
    if role not in allowed_roles:
        raise ValueError("Choose a valid employee role.")
    if not email.lower().endswith("@nust.ac.zw"):
        raise ValueError("Only individually verified @nust.ac.zw staff addresses can be invited.")
    headers = {"apikey": SUPABASE_SERVICE_ROLE_KEY,
               "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
               "Content-Type": "application/json"}
    invite = requests.post(
        f"{SUPABASE_URL}/auth/v1/invite",
        headers=headers,
        json={"email": email, "data": {"full_name": full_name}},
        timeout=15,
    )
    if invite.status_code >= 400:
        if invite.status_code == 422:
            raise ValueError("This email may already have an account or invitation. Review it in Supabase Auth.")
        invite.raise_for_status()
    invited_user = invite.json()
    user_id = invited_user.get("id") or invited_user.get("user", {}).get("id")
    if not user_id:
        raise AuthenticationUnavailable("Supabase sent an invitation but did not return a user ID.")
    profile = requests.post(
        f"{SUPABASE_URL}/rest/v1/employee_profiles",
        headers={**headers, "Prefer": "return=minimal"},
        json={"user_id": user_id, "email": email, "full_name": full_name,
              "role": role, "is_active": True, "invited_by": invited_by},
        timeout=15,
    )
    if profile.status_code >= 400:
        raise AuthenticationUnavailable(
            "The invitation was sent, but the employee profile could not be created. "
            "Do not resend it; inspect the employee_profiles table and Supabase Auth user."
        )
