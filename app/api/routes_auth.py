"""Auth routes."""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth_flow import RegisteredUsersResponse, SignInRequest, SignUpRequest, UserProfileResponse
from app.services.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sign-up", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpRequest, db: Session = Depends(get_db)) -> User:
    if db.scalars(select(User).where(User.phone == payload.phone)).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone already registered.",
        )
    user = User(
        full_name=payload.full_name,
        phone=payload.phone,
        sex=payload.sex,
        date_of_birth=payload.date_of_birth,
        nationality=payload.nationality.strip(),
        occupation=payload.occupation,
        business_type=payload.business_type,
        monthly_income=payload.monthly_income,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/sign-in", response_model=UserProfileResponse)
def sign_in(payload: SignInRequest, db: Session = Depends(get_db)) -> User:
    user = db.scalars(select(User).where(User.phone == payload.phone)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password.",
        )
    return user


@router.get("/registered-users", response_model=RegisteredUsersResponse)
def list_registered_users(
    _: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
    db: Session = Depends(get_db),
) -> RegisteredUsersResponse:
    """Return paginated registered users (safe profile fields only)."""
    total = int(db.scalar(select(func.count(User.id))) or 0)
    users = list(
        db.scalars(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        ).all()
    )
    return RegisteredUsersResponse(total=total, limit=limit, offset=offset, users=users)
