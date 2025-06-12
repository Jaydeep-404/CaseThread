from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from models.user import (
    UserResponse, OTPVerify, Token, PasswordUpdate, PasswordLogin, UserBase,
    SetPasswordAfterVerification, EmailRequest
)
from database import get_database
from security import (
    generate_otp,
    create_access_token,
    verify_token,
    verify_password,
    get_password_hash,
    OTP_EXPIRY_MINUTES
)
from config import settings
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from helper.email_sender import send_email_async
import uuid
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


# Helper functions
async def get_user_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    """Get user by email from database."""
    return await db.users.find_one({"email": email})


async def authenticate_user_with_otp(db, email: str, otp: str) -> Optional[Dict[str, Any]]:
    """Authenticate user with email and OTP."""
    # Get the user record with valid OTP
    user = await db.users.find_one({
        "email": email,
        "otp": otp,
        "otp_expires_at": {"$gt": datetime.now(timezone.utc)}
    })
    
    return user


async def authenticate_user_with_password(db, email: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate user with email and password."""
    # Get the user record
    user = await db.users.find_one({"email": email})
    
    if not user or not user.get("password"):
        return None
    
    # Verify hashed password
    if not verify_password(password, user["password"]):
        return None
    
    return user


async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_database)):
    """Get current user from token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    
    email = payload.get("email", "")
    if not email:
        raise credentials_exception
    
    user = await get_user_by_email(db, email)
    if user is None:
        raise credentials_exception
    
    return user


@router.post("/register", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def register(user: UserBase, background_tasks: BackgroundTasks, db = Depends(get_database)):
    """Register a new user with password."""
    # Check if user already exists
    password_user = await db.users.find_one({
        "email": user.email,
        "is_verified": True,
        "password": {"$exists": True}
    })
    
    if password_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    
    # Generate OTP for email verification
    otp = generate_otp()
    otp_expires = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    # Create new user with OTP for verification
    user_dict = user.model_dump()
    
    subject = "Verify your email"
    recipient = user.email
    body = f"Your OTP for email verification is: {otp}"
    
    without_pass_user = await db.users.find_one({"email": user.email})
    
    if without_pass_user:
        # Update the existing unverified user
        await db.users.update_one(
            {"_id": without_pass_user["_id"]},
            {"$set": {
                "otp": otp,
                "otp_expires_at": otp_expires,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
   
        user_response = {
            "name": without_pass_user["name"],
            "email": without_pass_user["email"]
        }
        # Send verification email
        background_tasks.add_task(send_email_async, subject, recipient, body)
        
        # In development mode, return the OTP
        return {
            "message": "User registered successfully. Please verify your email with the OTP.",
            "user": user_response
        }
    
    user_dict["is_verified"] = False
    user_dict["created_at"] = datetime.now(timezone.utc)
    user_dict["updated_at"] = datetime.now(timezone.utc)
    user_dict["otp"] = otp
    user_dict["otp_expires_at"] = otp_expires
    
    # Insert user into database
    result = await db.users.insert_one(user_dict)
    
    # Get the created user
    created_user = await db.users.find_one({"_id": result.inserted_id})
    
    if created_user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve created user"
        )
    
    # Convert ObjectId to string for response
    user_response = {
        "name": created_user["name"],
        "email": created_user["email"]
    }
    
    # In development mode, return the OTP
    response = {
        "message": "User registered successfully. Please verify your email with the OTP.",
        "user": user_response
    }
    # Send verification email
    background_tasks.add_task(send_email_async, subject, recipient, body)
    # if settings.DEV_MODE:
    #     response["otp"] = otp
    #     response["otp_expires_at"] = str(otp_expires)  # Convert to string
    
    return response


@router.post("/verify", response_model=UserResponse)
async def verify_otp(otp_data: OTPVerify, db = Depends(get_database)):
    """Verify user with OTP."""
    # Get the user with valid OTP
    user = await db.users.find_one({
        "email": otp_data.email,
        "otp": otp_data.otp,
        "otp_expires_at": {"$gt": datetime.now(timezone.utc)}
    })
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )
    
    # Generate verification ID
    verification_id = str(uuid.uuid4())
    # Prepare update data - mark as verified and clear OTP
    update_data = {
        "verification_id": verification_id,
        "is_verified": True,
        "updated_at": datetime.now(timezone.utc)
    }
    
    # Update user
    update_result = await db.users.update_one(
        {"email": otp_data.email},
        {
            "$set": update_data,
            "$unset": {
                "otp": "",
                "otp_expires_at": ""
            }
        }
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get the updated user
    updated_user = await get_user_by_email(db, otp_data.email)
    
    if updated_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Convert ObjectId to string for response
    user_response = {
        "id": verification_id,
        "name": updated_user["name"],
        "email": updated_user["email"],
        "is_verified": updated_user["is_verified"],
        "created_at": updated_user["created_at"]
    }
    
    return UserResponse(**user_response)


@router.post("/login", response_model=Token)
async def login(login_data: PasswordLogin, db = Depends(get_database)):
    """Login with email and password."""
    # Get the user record first
    user = await get_user_by_email(db, login_data.email)
    
    # Check if user exists
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Make sure user is verified before allowing login
    if not user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email is not verified. Please verify your email first.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Make sure user has a password set
    if not user.get("password"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password not set. Please set a password for your account.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Authenticate with password
    if not verify_password(login_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": user["email"]}
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/request-otp", response_model=Dict[str, Any])
async def request_otp(email_request: EmailRequest, background_tasks: BackgroundTasks, db = Depends(get_database)):
    """Request a new OTP."""
    req_email = email_request.email
    print(req_email)
    # Check if user exists
    user = await get_user_by_email(db, req_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Generate new OTP
    otp = generate_otp()
    otp_expires = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    # Update user with new OTP
    await db.users.update_one(
        {"email": req_email},
        {
            "$set": {
                "otp": otp,
                "otp_expires_at": otp_expires,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    response = {"message": "OTP sent to your email"}
    subject = "Verify your email"
    recipient = user.get("email")
    
    body = f"Your OTP for email verification is: {otp}"
    background_tasks.add_task(send_email_async, subject, recipient, body)
    # In development mode, return the OTP
    # if settings.DEV_MODE:
    #     response["otp"] = otp
    #     response["otp_expires_at"] = str(otp_expires)  # Convert to string
    
    return response


@router.get("/user-profile", response_model=UserResponse)
async def read_users_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user information."""
    # Handle the case where current_user might be None
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_response = {
        "id": str(current_user["_id"]),
        "name": current_user["name"],
        "email": current_user["email"],
        "is_verified": current_user["is_verified"],
        "created_at": current_user["created_at"]
    }
    
    return UserResponse(**user_response)


@router.post("/set-password", response_model=Dict[str, str])
async def set_password_after_verification(
    data: SetPasswordAfterVerification,
    db = Depends(get_database)
):
    """Set password after email verification."""
    # Check if user exists and is verified
    user = await db.users.find_one({
        "verification_id": str(data.id),
        "is_verified": True
    })
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found or not verified"
        )
    
    # Hash the password
    hashed_password = get_password_hash(data.password)
    
    # Update user - set password
    update_result = await db.users.update_one(
        {"verification_id": data.id},
        {
            "$set": {
                "password": hashed_password,
                "updated_at": datetime.now(timezone.utc)
            },
            "$unset": {"verification_id": "" }
        }
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Failed to update user"
        )
    
    return {"message": "Password set successfully. You can now log in."}


@router.post("/update-password", response_model=Dict[str, str])
async def update_password(
    password_data: PasswordUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db = Depends(get_database)
):
    """Update existing password for authenticated user."""
    # First, check if the user is verified
    if not current_user.get("is_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User must be verified to update a password"
        )
    
    # If current password is provided, verify it
    if password_data.current_password:
        stored_password = current_user.get("password")
        if not stored_password or not verify_password(password_data.current_password, stored_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )
    # If no current password is provided, only allow if user doesn't have a password set
    elif current_user.get("password"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is required"
        )
    
    # Hash the new password
    hashed_password = get_password_hash(password_data.new_password)
    
    # Update the user's password
    await db.users.update_one(
        {"email": current_user["email"]},
        {
            "$set": {
                "password": hashed_password,
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )
    
    return {"message": "Password updated successfully"}