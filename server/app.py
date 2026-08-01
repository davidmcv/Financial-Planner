"""Pension-planner backend: accounts, profile sync/sharing, reference data.

Run locally:
    uvicorn server.app:app --reload
Serves the single-page client at / and a JSON API under /api. Storage is
relational (SQLite by default; set DATABASE_URL to a PostgreSQL URL in
production - the schema and queries are identical).
"""
import datetime
import hashlib
import json
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import AuthToken, Base, Profile, ProfileShare, ReferenceDoc, User, utcnow
from .reference_data import REFERENCE_VERSION, reference_payload

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///pension_planner.db")
TOKEN_TTL_DAYS = int(os.environ.get("TOKEN_TTL_DAYS", "30"))
CLIENT_FILE = Path(__file__).resolve().parent.parent / "pension-planner.html"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

app = FastAPI(title="Pension Planner API", version=REFERENCE_VERSION)


# ---------------------------------------------------------------------------
# Startup: create tables and (re)seed reference data at the current version.
# ---------------------------------------------------------------------------
@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        doc = db.scalar(select(ReferenceDoc).where(ReferenceDoc.key == "reference"))
        payload = json.dumps(reference_payload())
        if doc is None:
            db.add(ReferenceDoc(key="reference", version=REFERENCE_VERSION, data=payload))
        elif doc.version != REFERENCE_VERSION:
            doc.version = REFERENCE_VERSION
            doc.data = payload
        db.commit()


def get_db():
    with SessionLocal() as db:
        yield db


# ---------------------------------------------------------------------------
# Auth helpers: scrypt password hashes, SHA-256-stored bearer tokens.
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=2 ** 14, r=8, p=1)
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def issue_token(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(AuthToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=utcnow() + datetime.timedelta(days=TOKEN_TTL_DAYS),
    ))
    db.commit()
    return raw


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token_hash = hashlib.sha256(header[7:].encode()).hexdigest()
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash))
    if token is None:
        raise HTTPException(401, "Invalid token")
    expires = token.expires_at
    if expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=datetime.timezone.utc)
    if expires < utcnow():
        raise HTTPException(401, "Token expired")
    return db.get(User, token.user_id)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class ShareRequest(BaseModel):
    email: EmailStr
    permission: str = Field(default="read", pattern="^(read|write)$")


# ---------------------------------------------------------------------------
# Health & reference data
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "version": REFERENCE_VERSION}


@app.get("/api/reference")
def reference(db: Session = Depends(get_db)):
    doc = db.scalar(select(ReferenceDoc).where(ReferenceDoc.key == "reference"))
    if doc is None:  # startup seeds it; belt and braces
        return reference_payload()
    return json.loads(doc.data)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.post("/api/auth/register")
def register(creds: Credentials, db: Session = Depends(get_db)):
    email = creds.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with that email already exists")
    user = User(email=email, password_hash=hash_password(creds.password))
    db.add(user)
    db.commit()
    return {"token": issue_token(db, user), "email": user.email}


@app.post("/api/auth/login")
def login(creds: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == creds.email.lower()))
    if user is None or not verify_password(creds.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": issue_token(db, user), "email": user.email}


@app.post("/api/auth/logout")
def logout(request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(request.headers["Authorization"][7:].encode()).hexdigest()
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash))
    if token:
        db.delete(token)
        db.commit()
    return {"status": "signed out"}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email}


# ---------------------------------------------------------------------------
# Profiles: per-user documents, synced by name; plus adviser/client sharing.
# ---------------------------------------------------------------------------
def own_profile(db: Session, user: User, name: str) -> Profile | None:
    return db.scalar(select(Profile).where(
        Profile.user_id == user.id, Profile.name == name))


@app.get("/api/profiles")
def list_profiles(user: User = Depends(current_user), db: Session = Depends(get_db)):
    own = {p.name: json.loads(p.data)
           for p in db.scalars(select(Profile).where(Profile.user_id == user.id))}
    shared = []
    rows = db.scalars(select(ProfileShare).where(ProfileShare.shared_with_id == user.id))
    for share in rows:
        shared.append({
            "owner": share.profile.owner.email,
            "name": share.profile.name,
            "permission": share.permission,
            "data": json.loads(share.profile.data),
        })
    return {"profiles": own, "shared": shared}


@app.put("/api/profiles/{name}")
def put_profile(name: str, data: dict, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    if not name.strip() or len(name) > 120:
        raise HTTPException(422, "Profile name must be 1-120 characters")
    profile = own_profile(db, user, name)
    if profile is None:
        profile = Profile(user_id=user.id, name=name)
        db.add(profile)
    profile.data = json.dumps(data)
    db.commit()
    return {"status": "saved", "name": name}


@app.delete("/api/profiles/{name}")
def delete_profile(name: str, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    profile = own_profile(db, user, name)
    if profile is None:
        raise HTTPException(404, "No such profile")
    db.delete(profile)
    db.commit()
    return {"status": "deleted", "name": name}


@app.post("/api/profiles/{name}/share")
def share_profile(name: str, req: ShareRequest, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    profile = own_profile(db, user, name)
    if profile is None:
        raise HTTPException(404, "No such profile")
    target = db.scalar(select(User).where(User.email == req.email.lower()))
    if target is None:
        raise HTTPException(404, "No account with that email")
    if target.id == user.id:
        raise HTTPException(422, "Profile is already yours")
    share = db.scalar(select(ProfileShare).where(
        ProfileShare.profile_id == profile.id,
        ProfileShare.shared_with_id == target.id))
    if share is None:
        share = ProfileShare(profile_id=profile.id, shared_with_id=target.id)
        db.add(share)
    share.permission = req.permission
    db.commit()
    return {"status": "shared", "name": name, "with": target.email,
            "permission": req.permission}


@app.delete("/api/profiles/{name}/share/{email}")
def unshare_profile(name: str, email: str, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    profile = own_profile(db, user, name)
    if profile is None:
        raise HTTPException(404, "No such profile")
    target = db.scalar(select(User).where(User.email == email.lower()))
    share = target and db.scalar(select(ProfileShare).where(
        ProfileShare.profile_id == profile.id,
        ProfileShare.shared_with_id == target.id))
    if not share:
        raise HTTPException(404, "Not shared with that email")
    db.delete(share)
    db.commit()
    return {"status": "unshared", "name": name, "with": email.lower()}


@app.put("/api/shared/{owner_email}/{name}")
def update_shared_profile(owner_email: str, name: str, data: dict,
                          user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    """Write access to a profile someone shared with you (permission=write)."""
    owner = db.scalar(select(User).where(User.email == owner_email.lower()))
    profile = owner and db.scalar(select(Profile).where(
        Profile.user_id == owner.id, Profile.name == name))
    if profile is None:
        raise HTTPException(404, "No such profile")
    share = db.scalar(select(ProfileShare).where(
        ProfileShare.profile_id == profile.id,
        ProfileShare.shared_with_id == user.id))
    if share is None:
        raise HTTPException(403, "Profile is not shared with you")
    if share.permission != "write":
        raise HTTPException(403, "You have read-only access to this profile")
    profile.data = json.dumps(data)
    db.commit()
    return {"status": "saved", "name": name, "owner": owner.email}


# ---------------------------------------------------------------------------
# Client: the same single file, served at the root.
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
@app.get("/pension-planner.html", include_in_schema=False)
def client():
    return FileResponse(CLIENT_FILE, media_type="text/html")
