import os
import random
import string
import secrets
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import Optional
from config import settings

# Password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OTP settings
OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10

# JWT settings
SECRET_KEY = settings.SECRET_KEY if hasattr(settings, "SECRET_KEY") else secrets.token_hex(32)
ALGORITHM = str(os.getenv("ALGORITHM", "HS256"))
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))

def verify_password(plain_password, hashed_password):
    """Verify password."""
    if not plain_password or not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Get password hash."""
    if not password:
        return None
    return pwd_context.hash(password)

def generate_otp():
    """Generate a 6 digit OTP."""
    return ''.join(random.choices(string.digits, k=OTP_LENGTH))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt

def verify_token(token: str):
    """Verify token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        
        if sub is None:
            return None
        
        email = str(sub)  # Ensure email is a string
        exp = payload.get("exp")
        
        token_data = {"email": email, "exp": exp}
        return token_data
    except JWTError:
        return None