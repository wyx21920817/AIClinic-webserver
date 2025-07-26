from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    full_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "username": "johndoe",
                "email": "john@example.com",
                "role": "doctor",
                "created_at": "2025-04-10T12:00:00",
                "updated_at": "2025-04-10T12:00:00"
            }
        }

class AuditLogResponse(BaseModel):
    id: str
    timestamp: datetime
    user_id: str
    username: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: str

class PaginatedResponse(BaseModel):
    items: List[AuditLogResponse]
    pagination: dict
