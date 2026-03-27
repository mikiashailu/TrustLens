import uuid

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db


def get_current_user(
    user_id: uuid.UUID = Query(
        ...,
        description="User UUID from sign-up or sign-in.",
    ),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the user from the `user_id` query parameter (demo / hackathon style — not a secure auth model)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No user found for that id.",
        )
    return user
