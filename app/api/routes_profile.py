from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.db.models import User
from app.schemas.auth_flow import UserProfileResponse

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=UserProfileResponse)
def get_profile(current_user: User = Depends(get_current_user)) -> User:
    """Who am I — uses `user_id` query param (same as other protected routes)."""
    return current_user
