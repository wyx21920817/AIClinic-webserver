from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
import jwt
from datetime import datetime, timedelta
import os
from fastapi.responses import Response
import json
import logging
from ..core.logging import AuditLog

router = APIRouter(
    prefix="/api/auth",
    tags=["authentication"],
    dependencies=[]
)

# Configure logger
logger = logging.getLogger(__name__)

# Get key from environment variables
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-secret-key')

@router.get('/verify-token')
@router.post('/verify-token')
async def verify_token(authorization: str = Header(None)):
    """
    Endpoint for validating JWT tokens, used by Orthanc callbacks
    Supports validation of regular tokens and temporary tokens
    """
    logger.info(f"Received token verification request")
    
    if not authorization:
        logger.warning("No authorization header provided")
        return JSONResponse(
            status_code=401,
            content={"detail": "No authorization header"}
        )
    
    try:
        # Parse token
        token = authorization.split(' ')[1] if ' ' in authorization else authorization
        logger.debug(f"Processing token verification")
        
        # Validate token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=['HS256'])
        
        # Check if token is expired
        exp = payload.get('exp')
        if exp and datetime.utcnow().timestamp() > exp:
            logger.warning("Token has expired")
            return JSONResponse(
                status_code=401,
                content={"detail": "Token has expired"}
            )
        
        # Build basic response
        response_data = {
            "granted": True,
            "validity": 3600,  # Default cache 1 hour
            "labels": ["view"],  # Basic view permission
            "user": payload.get('sub', 'unknown'),
            "is_temp": False
        }
        
        # Handle temporary token
        if payload.get('temp', False) and payload.get('orthanc_access', False):
            response_data.update({
                "validity": 60,  # Temporary token cached for 1 minute only
                "labels": ["view", "upload", "modify", "all"],
                "user": "orthanc_temp_access",
                "is_temp": True
            })
            logger.info("Processed temporary token")
            return JSONResponse(content=response_data)
        
        # Handle regular token
        sub = payload.get('sub')
        if not sub:
            logger.warning("Token missing subject claim")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid token structure"}
            )
        
        # Set permissions
        role = payload.get('role', '')
        if role in ['doctor', 'admin']:
            response_data['labels'].append("upload")
        if role == 'admin':
            response_data['labels'].extend(["all", "modify"])
        
        logger.info(f"Successful token verification for user {sub} with role {role}")
        
        # Record audit log
        AuditLog.log_auth(
            user_id=sub,
            action="verify_token",
            details=f"Token verification for user {sub} with role {role}",
            username=payload.get('username', sub)
        )
        
        return JSONResponse(content=response_data)
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token signature has expired")
        return JSONResponse(
            status_code=401,
            content={"detail": "Token has expired"}
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid token"}
        )
    except Exception as e:
        logger.error(f"Unexpected error in token verification: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )

@router.get('/temp-token')
async def get_temp_token():
    """
    Generate a temporary token with a validity period of 1 minute, 
    which has the permission to query and modify Orthanc files
    """
    try:
        # Create token payload
        payload = {
            'exp': datetime.utcnow() + timedelta(minutes=1),  # Expires in 1 minute
            'iat': datetime.utcnow(),
            'temp': True,  # Mark as temporary token
            'orthanc_access': True  # Mark this token for Orthanc access
        }
        
        # Generate token
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256')
        
        # Record audit log
        AuditLog.log_auth(
            user_id="system",
            action="generate_temp_token",
            details="Generated temporary token for Orthanc access",
            username="system"
        )
        
        return JSONResponse(
            content={
                "token": token,
                "expires_in": 60,  # 60 seconds
                "token_type": "Bearer"
            },
            status_code=200
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))