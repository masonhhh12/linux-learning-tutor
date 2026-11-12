"""SQLite accounts and opaque cookie sessions for the local tutor."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr, field_validator

DB_PATH = Path(os.environ.get("TUTOR_DB_PATH", Path(__file__).parent / "data" / "tutor.sqlite3"))
SECURE_COOKIES = os.environ.get("TUTOR_SECURE_COOKIES", "0") == "1"
COOKIE = "__Host-tutor_session" if SECURE_COOKIES else "tutor_session"
SESSION_SECONDS = 8 * 60 * 60
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
router = APIRouter(prefix="/auth", tags=["accounts"])


@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Create with owner-only permissions before SQLite can write credentials.
    descriptor = os.open(DB_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(descriptor)
    os.chmod(DB_PATH, 0o600)
    with database() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_attempts (
                bucket TEXT NOT NULL,
                attempted_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS attempts_lookup
                ON auth_attempts(bucket, attempted_at);
        """)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token):
    return digest("csrf:" + token)


def check_origin(request: Request):
    origin = request.headers.get("origin")
    expected = str(request.base_url).rstrip("/")
    if origin != expected or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Request origin is not allowed.")


def rate_limit(request, username, action):
    # Count real peer IPs, never an untrusted X-Forwarded-For header.
    peer = request.client.host if request.client else "unknown"
    buckets = [(digest(action + ":ip:" + peer), 30 if action == "login" else 10)]
    if action == "login":
        buckets.append((digest("login:user:" + username), 10))
    now = int(time.time())
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM auth_attempts WHERE attempted_at < ?", (now - 900,))
        for bucket, limit in buckets:
            count = db.execute("SELECT COUNT(*) FROM auth_attempts WHERE bucket = ?", (bucket,)).fetchone()[0]
            if count >= limit:
                raise HTTPException(429, "Too many attempts. Try again in 15 minutes.",
                                    headers={"Retry-After": "900"})
        db.executemany("INSERT INTO auth_attempts(bucket, attempted_at) VALUES (?, ?)",
                       [(bucket, now) for bucket, _ in buckets])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        value = value.lower()
        if not re.fullmatch(r"[a-z0-9_]{3,32}", value):
            raise ValueError("Use 3–32 letters, numbers, or underscores.")
        return value


def get_session(request):
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 128:
        return None
    with database() as db:
        row = db.execute("""
            SELECT users.id, users.username, sessions.expires_at
            FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
        """, (digest(token), int(time.time()))).fetchone()
    return dict(row) if row else None


def require_session(request: Request):
    user = get_session(request)
    if not user:
        raise HTTPException(401, "Please sign in.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        check_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(supplied, csrf_token(request.cookies[COOKIE])):
            raise HTTPException(403, "Invalid request token. Refresh and try again.")
    return user


def new_session(request, response, user_id):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with database() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        previous = request.cookies.get(COOKIE)
        if previous:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(previous),))
        db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                   (digest(token), user_id, now + SESSION_SECONDS))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=SECURE_COOKIES, samesite="strict", path="/")
    return csrf_token(token)


@router.post("/register", status_code=201)
def register(credentials: Credentials, request: Request, response: Response):
    check_origin(request)
    rate_limit(request, credentials.username, "register")
    password = credentials.password.get_secret_value()
    if len(password) < 15:
        raise HTTPException(422, "Use a password or passphrase of at least 15 characters.")
    password_hash = hasher.hash(password)
    try:
        with database() as db:
            cursor = db.execute(
                "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                (credentials.username, password_hash, int(time.time())))
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Unable to create that account. Try a different username.") from None
    csrf = new_session(request, response, user_id)
    return {"username": credentials.username, "csrf_token": csrf}


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response):
    check_origin(request)
    rate_limit(request, credentials.username, "login")
    with database() as db:
        row = db.execute("SELECT id,password_hash FROM users WHERE username = ?",
                         (credentials.username,)).fetchone()
    try:
        hasher.verify(row["password_hash"] if row else DUMMY_HASH,
                      credentials.password.get_secret_value())
        valid = row is not None
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid:
        raise HTTPException(401, "Invalid username or password.")
    if hasher.check_needs_rehash(row["password_hash"]):
        updated = hasher.hash(credentials.password.get_secret_value())
        with database() as db:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (updated, row["id"]))
    csrf = new_session(request, response, row["id"])
    return {"username": credentials.username, "csrf_token": csrf}


@router.get("/me")
def me(request: Request, user=Depends(require_session)):
    return {"username": user["username"], "csrf_token": csrf_token(request.cookies[COOKIE])}


@router.post("/logout", status_code=204)
def logout(request: Request, user=Depends(require_session)):
    with database() as db:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (digest(request.cookies[COOKIE]),))
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/", secure=SECURE_COOKIES,
                           httponly=True, samesite="strict")
    return response
