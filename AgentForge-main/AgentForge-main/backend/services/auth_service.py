
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from backend.core.config import settings
from backend.core.exceptions import AuthenticationError, ConfigurationError

TOKEN_TYPE = "bearer"


class AuthService:
    def __init__(self, *, secret: str | None = None, algorithm: str | None = None) -> None:
        self.secret = secret or settings.JWT_SECRET
        self.algorithm = algorithm or settings.JWT_ALGORITHM

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))

    def create_access_token(self, *, subject: str) -> str:
        if not self.secret:
            raise ConfigurationError("JWT_SECRET is not configured; cannot issue access tokens.")

        expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {"sub": subject, "exp": expire, "iat": datetime.now(UTC)}

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def decode_access_token(self, token: str) -> dict[str, Any]:
        if not self.secret:
            raise ConfigurationError("JWT_SECRET is not configured; cannot verify access tokens.")

        try:
            return jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except jwt.PyJWTError as error:
            raise AuthenticationError("Invalid or expired access token.") from error