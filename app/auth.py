from fastapi import Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def get_optional_user(request: Request, db: Session) -> models.User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(models.User, user_id)
