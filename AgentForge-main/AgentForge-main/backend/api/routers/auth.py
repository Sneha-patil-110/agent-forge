
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_application, get_current_user, get_db_session
from backend.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from backend.core.app import Application
from backend.db.models.user import User
from backend.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    application: Application = Depends(get_application),
    session: Session = Depends(get_db_session),
) -> UserOut:
    repository = UserRepository(session)

    if repository.get_by_email(payload.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    user = repository.create(
        email=payload.email,
        hashed_password=application.auth_service.hash_password(payload.password),
    )

    return UserOut(id=user.id, email=user.email, created_at=user.created_at)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    application: Application = Depends(get_application),
    session: Session = Depends(get_db_session),
) -> TokenResponse:
    user = UserRepository(session).get_by_email(payload.email)

    if user is None or not application.auth_service.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    token = application.auth_service.create_access_token(subject=str(user.id))

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, created_at=user.created_at)