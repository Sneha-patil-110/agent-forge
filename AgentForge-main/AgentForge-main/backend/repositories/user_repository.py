from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, email: str, hashed_password: str) -> User:
        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hashed_password,
            created_at=datetime.now(UTC),
        )
        self.session.add(user)
        self.session.flush()

        return user

    def get_by_email(self, email: str) -> User | None:
        query = select(User).where(User.email == email)

        return self.session.execute(query).scalar_one_or_none()

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)