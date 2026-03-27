import uuid

from pydantic import BaseModel, Field


class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(..., min_length=5, max_length=32)
    sex: str = Field(..., min_length=1, max_length=32)
    occupation: str = Field(..., min_length=1, max_length=255)
    business_type: str = Field(..., min_length=1, max_length=255)
    monthly_income: float = Field(..., ge=0, le=1_000_000_000)
    password: str = Field(..., min_length=6, max_length=128)


class SignInRequest(BaseModel):
    phone: str = Field(..., min_length=5, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: str
    sex: str
    occupation: str
    business_type: str
    monthly_income: float

    model_config = {"from_attributes": True}


class RegisteredUsersResponse(BaseModel):
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=200)
    offset: int = Field(..., ge=0)
    users: list[UserProfileResponse]
