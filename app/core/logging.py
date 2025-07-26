"""
Audit logging system for tracking user actions and system events.
"""
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request
from ..model.audit_log import AuditLogEntry

class AuditLog:
    @staticmethod
    def log_event(
        event_type: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
        username: Optional[str] = None
    ) -> None:
        """
        Log an audit event.

        Args:
            event_type: Type of event (auth, data_access, api_call)
            user_id: ID of the user performing the action
            action: Action being performed (login, view, modify, delete)
            resource_type: Type of resource being accessed (patient, study, instance)
            resource_id: Optional ID of the resource being accessed
            details: Optional additional details about the event
            status: Outcome of the action (success, failure)
            request: Optional FastAPI request object for additional context
        """
        # Create log entry document
        log_entry = AuditLogEntry(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            details=str(details) if details else "",
        username=username
        )

        # No request context in this version
        log_entry.request_info = {}

        # Save to MongoDB
        log_entry.save()

    @staticmethod
    def log_auth(user_id: str, action: str, status: str = "success", details: Optional[Dict[str, Any]] = None, username: Optional[str] = None):
        """Log authentication events"""
        AuditLog.log_event("auth", user_id, action, "user", None, details, status, username)

    @staticmethod
    def log_data_access(user_id: str, action: str, resource_type: str, resource_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None, username: Optional[str] = None):
        """Log data access events"""
        AuditLog.log_event("data_access", user_id, action, resource_type, resource_id, details, "success", username)

    @staticmethod
    def log_api_call(user_id: str, action: str, api_endpoint: str, details: Optional[Dict[str, Any]] = None, username: Optional[str] = None):
        """Log API usage events"""
        AuditLog.log_event("api_call", user_id, action, "api", api_endpoint, details, "success", username)
