from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import List, Optional
from datetime import datetime, timedelta
import jwt
import random
import string
from pydantic import BaseModel 
import re
from ..model.user import User, UserRole
import os
from dotenv import load_dotenv
from ..core.config import settings
from .utils.mail import send_verification_email

load_dotenv()

# JWT configuration
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES

# OAuth2 scheme for JWT
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login/mfa")

# Router
router = APIRouter(
    prefix="/api",
    tags=["users"],
    responses={404: {"description": "Not found"}}
)

class UserLogin(BaseModel):
    username: str
    password: str

class MFAVerify(BaseModel):
    username: str
    mfa_code: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: UserRole
    created_at: datetime

    class Config:
        schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "username": "johndoe",
                "email": "john@example.com",
                "role": "doctor",
                "created_at": "2025-04-10T12:00:00"
            }
        }

def generate_mfa_code(username: str = None):
    """Generate a 6-digit verification code
    If username is '123', returns fixed code '111111' for testing purposes"""
    if username == '123':
        return '111111'
    return ''.join(random.choices(string.digits, k=6))

def create_access_token(data: dict):
    """Create JWT token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate JWT token and return current user"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # 检查是否是临时token
        if payload.get('temp', False):
            raise HTTPException(
                status_code=401,
                detail="Temporary tokens cannot be used for user authentication"
            )
            
        # 检查sub字段
        if "sub" not in payload:
            raise HTTPException(
                status_code=401,
                detail="Invalid token content - missing user identifier"
            )
            
        user = User.objects(id=payload["sub"]).first()
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        # Add token to user object
        setattr(user, 'token', token)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

async def get_admin_user(current_user: User = Depends(get_current_user)):
    """Check if current user is admin"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

def is_valid_email(email: str) -> bool:
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

@router.post("/login", 
    summary="Login step 1 - Password verification",
    description="First step of login process. Validates username and password, then sends verification code to user's email.")
async def login(
    username: str = Form(..., description="Username of the account"),
    password: str = Form(..., description="Password of the account")
):
    """
    First step of the two-step login process:

    1. Validate username and password
    2. If valid, send verification code to user's email
    3. Return success message

    Use the verification code with /login/mfa endpoint to complete login.
    """
    user = User.objects(username=username).first()
    if not user or not user.verify_password(password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    # Generate and store verification code
    verification_code = generate_mfa_code(username)
    user.mfa_code = verification_code
    user.mfa_expires_at = datetime.utcnow() + timedelta(minutes=settings.MFA_EXPIRE_MINUTES)
    user.save()

    # Send verification code via email
    try:
        send_verification_email(user.email, verification_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to send verification email")

    return {"message": "Verification code sent to your email"}

@router.post("/login/mfa",
    summary="Login step 2 - Email verification",
    description="Second step of login process. Validates the email verification code and issues JWT token.")
async def verify_mfa(
    username: str = Form(..., description="Username of the account"),
    mfa_code: str = Form(..., description="6-digit verification code sent to email")
):
    """
    Second step of the two-step login process:

    1. Validate the verification code sent to email
    2. If valid, issue JWT token
    3. Return token for future API calls

    The token should be included in the Authorization header for protected endpoints.
    """
    user = User.objects(username=username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    print(f"Verifying MFA for user: {username}")
    print(f"Stored MFA code: {user.mfa_code}")
    print(f"Received MFA code: {mfa_code}")
    print(f"MFA expires at: {user.mfa_expires_at}")
    print(f"Current time: {datetime.utcnow()}")

    if not user.mfa_code:
        raise HTTPException(status_code=401, detail="No verification code found")
    
    if user.mfa_code != mfa_code:
        raise HTTPException(status_code=401, detail="Invalid verification code")
    
    if datetime.utcnow() > user.mfa_expires_at:
        raise HTTPException(status_code=401, detail="Verification code has expired")

    # Clear MFA code after successful verification
    user.mfa_code = None
    user.mfa_expires_at = None
    user.save()

    # Generate JWT token
    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return {"access_token": access_token, "token_type": "bearer", "user_id": str(user.id), "role": user.role.value, "username": user.username}

@router.get("/users", response_model=List[UserResponse],
    summary="Get all users",
    description="Get list of all users. Requires admin role.")
async def get_users(current_user: User = Depends(get_admin_user)):
    """
    Retrieve a list of all registered users.

    This endpoint requires admin privileges.
    Returns a list of users with their details (excluding passwords).
    """
    users = User.objects.all()
    return [UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at
    ) for user in users]

@router.get("/user/{user_id}", response_model=UserResponse,
    summary="Get user details",
    description="Get details of a specific user. Requires admin role or be the user themselves.")
async def get_user(user_id: str, current_user: User = Depends(get_current_user)):
    """
    Retrieve details of a specific user.

    - Admin can view any user's details
    - Regular users can only view their own details
    """
    if current_user.role != UserRole.ADMIN and str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    try:
        from bson import ObjectId
        user = User.objects(id=ObjectId(user_id)).first()
    except Exception as e:
        user = None

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at
    )

@router.post("/users", response_model=UserResponse,
    summary="Create new user",
    description="Create new user with username, password and email. Requires admin role.")
async def create_user(
    username: str = Form(..., description="Username for the new account"),
    password: str = Form(..., description="Password for the new account"),
    email: str = Form(..., description="Email address for verification"),
    role: UserRole = Form(..., description="User role (admin or doctor)"),
    current_user: User = Depends(get_admin_user)
):
    """
    Create new user with the following information:

    - **username**: Unique username for the account
    - **password**: Password for the account
    - **email**: Valid email address for verification
    - **role**: Role for the new user (admin only)

    This endpoint requires admin privileges.
    """
    if User.objects(username=username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    if User.objects(email=email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=username,
        email=email,
        role=role
    )
    user.set_password(password)
    user.save()

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at
    )

@router.put("/user/{user_id}", response_model=UserResponse,
    summary="Update user",
    description="Update user information. Requires admin role or be the user themselves.")
async def update_user(
    user_id: str,
    email: str = Form(None, description="New email address"),
    username: str = Form(None, description="New username"),
    password: str = Form(None, description="New password"),
    role: Optional[UserRole] = Form(None, description="New role (admin only)"),
    current_user: User = Depends(get_current_user)
):
    """
    Update user information. Can update:

    - **email**: New email address
    - **password**: New password
    - **role**: New role (admin only)

    Notes:
    - Admin can update any user
    - Regular users can only update themselves
    - Only admin can change user roles
    """
    if current_user.role != UserRole.ADMIN and str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    user = User.objects(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Only admin can change roles
    if role is not None and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admin can change user roles")

    # Update email if provided
    if email is not None:
        if not is_valid_email(email):
            raise HTTPException(status_code=400, detail="Invalid email format")
        if User.objects(email=email).first() and email != user.email:
            raise HTTPException(status_code=400, detail="Email already registered")
        user.email = email

    # Update password if provided
    if password is not None:
        user.set_password(password)

     # Update password if provided
    if username is not None:
        user.set_username(username)

    # Update role if provided (admin only)
    if role is not None:
        user.role = role

    user.updated_at = datetime.utcnow()
    user.save()

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at
    )

@router.delete("/user/{user_id}",
    summary="Delete user",
    description="Delete a user. Requires admin role or be the user themselves.")
async def delete_user(user_id: str, current_user: User = Depends(get_current_user)):
    """
    Delete a user account.

    Notes:
    - Admin can delete any user
    - Regular users can only delete themselves
    - Cannot delete the last admin user
    """
    if current_user.role != UserRole.ADMIN and str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Permission denied")

    user = User.objects(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting the last admin
    if user.role == UserRole.ADMIN and User.objects(role=UserRole.ADMIN).count() <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the last admin user")

    user.delete()
    return {"message": "User deleted successfully"}

@router.post("/register", response_model=UserResponse, status_code=201,
    summary="Register new user",
    description="Register a new user with username, password and email. New users are automatically assigned the doctor role.")
async def register(
    username: str = Form(..., description="Username for the new account"),
    password: str = Form(..., description="Password for the new account"),
    email: str = Form(..., description="Email address for verification")
):
    """
    Register a new user with the following information:

    - **username**: Unique username for the account
    - **password**: Password for the account
    - **email**: Valid email address for verification

    The user will be automatically assigned the role of doctor.
    """
    # Validate email format
    if not is_valid_email(email):
        raise HTTPException(status_code=422, detail="Invalid email format")

    # Check if username already exists
    if User.objects(username=username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Check if email already exists
    if User.objects(email=email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create new user with doctor role
    try:
        user = User(
            username=username,
            email=email,
            role=UserRole.DOCTOR  # 新注册用户默认为医生角色
        )
        user.set_password(password)
        user.save()

        return UserResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            role=user.role,
            created_at=user.created_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")
