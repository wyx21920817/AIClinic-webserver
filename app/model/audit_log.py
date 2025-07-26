from mongoengine import Document, StringField, DateTimeField, DictField
from datetime import datetime

class AuditLogEntry(Document):
    timestamp = DateTimeField(required=True, default=datetime.utcnow)
    event_type = StringField(required=True)  # auth, data_access, api_call
    user_id = StringField(required=True)
    action = StringField(required=True)
    resource_type = StringField(required=True)
    resource_id = StringField()
    status = StringField(required=True)
    username = StringField()
    details = StringField()
    request_info = DictField()

    meta = {
        'collection': 'audit_logs',
        'indexes': [
            'timestamp',
            'event_type',
            'user_id',
            'resource_type',
            'resource_id',
            'status'
        ]
    }
