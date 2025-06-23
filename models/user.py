from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
from typing import Optional
from datetime import datetime
import re


class UserBase(BaseModel):
    """Base user model"""
    name: str = Field(description="User's full name", max_length=50)
    email: EmailStr = Field(description="User's email address")


class UserResponse(UserBase):
    """User response model"""
    id: str
    is_verified: bool
    created_at: datetime
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "60d21b4967d0d8992e610c85",
                "name": "John Doe",
                "email": "john@example.com",
                "is_verified": False,
                "created_at": "2021-06-22T12:00:00"
            }
        }
    )


class OTPVerify(BaseModel):
    """OTP verification model"""
    email: EmailStr
    otp: str
    password: str = Field(None, min_length=8, description="Password to set after verification")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "otp": "123456",
                "password": "securepassword123"
            }
        }
    )


class Token(BaseModel):
    """Token model"""
    access_token: str
    token_type: str = "bearer"
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }
    )


class PasswordLogin(BaseModel):
    """User login with password model"""
    email: EmailStr
    password: str = Field(..., min_length=8)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "password": "your-secure-password"
            }
        }
    )


class UserLogin(BaseModel):
    """User login model (for backward compatibility)"""
    email: EmailStr
    otp: Optional[str] = None
    password: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "otp": "123456",
                # or alternatively:
                # "password": "your-secure-password"
            }
        }
    )

class PasswordUpdate(BaseModel):
    """Password update model for existing users"""
    current_password: Optional[str] = None
    new_password: str = Field(..., min_length=8)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_password": "oldpassword",
                "new_password": "newpassword123"
            }
        }
    )

class SetPasswordAfterVerification(BaseModel):
    """Model for setting password after verification"""
    id: str
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+]", v):
            raise ValueError("Password must contain at least one special character.")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "john@example.com",
                "password": "securepassword123"
            }
        }
    )
    
    
class EmailRequest(BaseModel):
    email: EmailStr
    

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    @field_validator("confirm_password")
    @classmethod
    def match(cls, v, info):
        if info.data.get("new_password") != v:
            raise ValueError("Passwords do not match.")
        return v