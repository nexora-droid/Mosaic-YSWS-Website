from datetime import datetime, timezone
from flask import request, session
from firebase_admin import firestore

class audit_logger:
    def __init__(self, db):
        self.db = db
    
    def log_action(self, action_type, user_id=None, user_name=None, details=None, target_user_id=None):
        log_entry = {
            'timestamp': datetime.now(timezone.utc),
            'action_type': action_type,
            'user_id': user_id,
            'user_name': user_name,
            'target_user_id': target_user_id,
            'details': details or {},
            'ip_address': request.remote_addr if request else None,
            'user_agent': request.headers.get('User-Agent') if request else None,
            'session_id': session.get('user_id') if session else None
        }
        
        try:
            self.db.collection('audit_logs').add(log_entry)
            print(f"[AUDIT LOG] {action_type} by {user_name or user_id}")
        except Exception as e:
            print(f"Error writing to audit log: {e}")
    
    def get_user_actions(self, user_id, limit=100):
        try:
            logs_ref = (self.db.collection('audit_logs')
                       .where('user_id', '==', user_id)
                       .order_by('timestamp', direction=firestore.Query.DESCENDING)
                       .limit(limit))
            
            logs = []
            for log in logs_ref.stream():
                log_data = log.to_dict()
                log_data['timestamp'] = log_data['timestamp'].isoformat()
                logs.append(log_data)
            
            return logs
        except Exception as e:
            print(f"Error reading audit log: {e}")
            return []
    
    def get_recent_actions(self, limit=100):
        try:
            logs_ref = (self.db.collection('audit_logs')
                       .order_by('timestamp', direction=firestore.Query.DESCENDING)
                       .limit(limit))
            
            logs = []
            for log in logs_ref.stream():
                log_data = log.to_dict()
                log_data['timestamp'] = log_data['timestamp'].isoformat()
                logs.append(log_data)
            
            return logs
        except Exception as e:
            print(f"Error reading audit log: {e}")
            return []
    
    def search_logs(self, action_type=None, user_id=None, start_date=None, end_date=None):
        try:
            logs_ref = self.db.collection('audit_logs')
            if action_type:
                logs_ref = logs_ref.where('action_type', '==', action_type)
            
            if user_id:
                logs_ref = logs_ref.where('user_id', '==', user_id)
            logs_ref = logs_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).limit(500)
            
            logs = []
            for log in logs_ref.stream():
                log_data = log.to_dict()
                timestamp = log_data['timestamp'].isoformat()
                
                if start_date and timestamp < start_date:
                    continue
                if end_date and timestamp > end_date:
                    continue
                
                log_data['timestamp'] = timestamp
                logs.append(log_data)
            
            return logs
        except Exception as e:
            print(f"Error searching audit log: {e}")
            return []

class ActionTypes:
    USER_LOGIN = 'USER_LOGIN'
    USER_LOGOUT = 'USER_LOGOUT'
    PROJECT_CREATE = 'PROJECT_CREATE'
    PROJECT_UPDATE = 'PROJECT_UPDATE'
    PROJECT_DELETE = 'PROJECT_DELETE'
    PROJECT_SUBMIT = 'PROJECT_SUBMIT'
    ADMIN_REVIEW_PROJECT = 'ADMIN_REVIEW_PROJECT'
    ADMIN_APPROVE_PROJECT = 'ADMIN_APPROVE_PROJECT'
    ADMIN_REJECT_PROJECT = 'ADMIN_REJECT_PROJECT'
    ADMIN_COMMENT_PROJECT = 'ADMIN_COMMENT_PROJECT'
    ADMIN_ASSIGN_PROJECT = 'ADMIN_ASSIGN_PROJECT'
    ADMIN_AWARD_TILES = 'ADMIN_AWARD_TILES'
    TILES_BALANCE_CHANGE = 'TILES_BALANCE_CHANGE'
    ADMIN_CREATE_THEME = 'ADMIN_CREATE_THEME'
    ADMIN_DELETE_THEME = 'ADMIN_DELETE_THEME'
    SUSPICIOUS_RAPID_ACTIONS = 'SUSPICIOUS_RAPID_ACTIONS'
    SUSPICIOUS_MULTIPLE_DELETES = 'SUSPICIOUS_MULTIPLE_DELETES'
    SUSPICIOUS_TILE_REQUEST = 'SUSPICIOUS_TILE_REQUEST'

