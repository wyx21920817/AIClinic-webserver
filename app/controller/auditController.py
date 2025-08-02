from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from app.model.audit_log import AuditLogEntry
from app.model.user import User, UserRole
from app.controller.userController import get_admin_user
from app.model.response import AuditLogResponse, PaginatedResponse
from mongoengine.queryset.visitor import Q

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[]
)

@router.get("/logs", 
    summary="Get audit logs", 
    description="Get paginated audit logs with optional filters.",
    response_model=PaginatedResponse
)
async def get_audit_logs(
    page: int = Query(1, description="Page number"),
    page_size: int = Query(20, description="Items per page"),
    start_date: Optional[datetime] = Query(None, description="Filter logs after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter logs before this date"),
    user_id: Optional[str] = Query(None, description="Filter logs by user ID"),
    action: Optional[str] = Query(None, description="Filter logs by action type"),
    resource_type: Optional[str] = Query(None, description="Filter logs by resource type"),
    current_user: User = Depends(get_admin_user)
):
    """
    Get paginated audit logs with optional filters.
    Only administrators can access this endpoint.
    """
    # Check if user is admin
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view audit logs"
        )

    # Build query filters
    query = Q()
    if start_date:
        query &= Q(timestamp__gte=start_date)
    if end_date:
        query &= Q(timestamp__lte=end_date)
    if user_id:
        query &= Q(user_id=user_id)
    if action:
        query &= Q(action=action)
    if resource_type:
        query &= Q(resource_type=resource_type)

    # Calculate skip and limit for pagination
    skip = (page - 1) * page_size
    
    # Get total count for pagination
    total_count = AuditLogEntry.objects(query).count()
    
    # Get paginated results
    audit_logs = AuditLogEntry.objects(query).order_by('-timestamp').skip(skip).limit(page_size)
    
    # Convert to response model
    response = []
    for log in audit_logs:
        response.append(AuditLogResponse(
            id=str(log.id),
            timestamp=log.timestamp,
            user_id=log.user_id,
            username=log.username or "system",  # If username is None, use "system"
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id or "",  # If resource_id is None, use empty string
            details=str(log.details) if log.details else ""  # Ensure details is a string
        ))
    
    # Add pagination headers
    total_pages = (total_count + page_size - 1) // page_size
    
    # Return paginated results
    return PaginatedResponse(
        items=response,
        pagination={
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    )
