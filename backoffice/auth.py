import os

import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
import models


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# The fallback is DEV ONLY and must be >= 32 bytes (HMAC-SHA256).
# In production, always set the SECRET_KEY environment variable.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-production-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def authenticate_user(db: Session, username: str, password: str):
    """Check a username / password pair at login.

    Return the user when both are valid, False otherwise. A soft-deleted
    account is treated as non-existent: it can no longer sign in.
    """
    user = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.deleted_at.is_(None))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        return False
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
):
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jeton invalide",
        )

    # Deleted accounts are excluded here too, so a token issued before the
    # deletion stops working immediately instead of lasting until it expires.
    user = (
        db.query(models.User)
        .filter(models.User.username == username, models.User.deleted_at.is_(None))
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé",
        )

    return user
