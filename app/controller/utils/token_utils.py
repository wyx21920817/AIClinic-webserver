from jose import jwt
from app.core.config import settings

def get_user_id_from_token(token: str) -> str:
    """
    Extract user ID from JWT token.
    
    Args:
        token (str): JWT token
        
    Returns:
        str: User ID or "system" if token is invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            return "system"
        return str(user_id)
    except Exception:
        return "system"

def get_user_info_from_token(token: str) -> tuple[str, str]:
    """
    Extract user ID and username from JWT token.
    
    Args:
        token (str): JWT token
        
    Returns:
        tuple[str, str]: Tuple of (user_id, username) or ("system", "system") if token is invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        username = payload.get("username")
        if not user_id:
            return "system", "system"
        return str(user_id), username or "unknown"
    except Exception:
        return "system", "system"
