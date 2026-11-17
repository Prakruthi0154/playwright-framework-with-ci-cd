from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import csrf_check, current_user, require_roles
from app.application.security import (
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_expiry,
    verify_password,
)
from app.config import settings
from app.db import get_db
from app.models.entities import RefreshToken, User
from app.schemas.contracts import AccessToken, LoginRequest, Role, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"


def issue_tokens(response: Response, db: Session, user: User) -> AccessToken:
    refresh_token = create_refresh_token()
    csrf_token = create_csrf_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expiry(),
        )
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.jwt_refresh_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/v1/auth",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=settings.jwt_refresh_days * 86400,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return AccessToken(access_token=create_access_token(user.id, user.role), csrf_token=csrf_token)


@router.post("/register", response_model=AccessToken, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    role = "admin" if db.scalar(select(func.count(User.id))) == 0 else "qa_engineer"
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.flush()
    tokens = issue_tokens(response, db, user)
    db.commit()
    return tokens


@router.post("/login", response_model=AccessToken)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    tokens = issue_tokens(response, db, user)
    db.commit()
    return tokens


@router.post("/refresh", response_model=AccessToken)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    csrf_check(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is missing")
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
    )
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is invalid or expired")
    now = datetime.now(UTC)
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if token.revoked_at is not None or expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token is invalid or expired")
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User is inactive or no longer exists")
    token.revoked_at = now
    result = issue_tokens(response, db, user)
    db.commit()
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    csrf_check(request)
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        token = db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_token))
        )
        if token is not None and token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
            db.commit()
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/api/v1/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(current_user)):
    return user


@router.get("/users", response_model=list[UserRead], tags=["administration"])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return list(db.scalars(select(User).order_by(User.created_at.desc())).all())


@router.patch("/users/{user_id}/role", response_model=UserRead, tags=["administration"])
def update_user_role(
    user_id: UUID,
    role: Role,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.role = role
    db.commit()
    db.refresh(user)
    return user
