import json
import os
from datetime import datetime, timezone
from functools import wraps
from flask import request, session

class AuditLogger:
    def __init__(self, log_file='logs/audit_log.json'):
        self.log_file = log_file
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                json.dump([], f)
    
    def log_action(self, action_type, user_id=None, user_name=None, details=None, target_user_id=None):
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
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
            with open(self.log_file, 'r') as f:
                logs = json.load(f)
            logs.append(log_entry)
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)
                
            print(f"[AUDIT LOG] {action_type} by {user_name or user_id}")
            
        except Exception as e:
            print(f"Error writing to audit log: {e}")
    
    def get_user_actions(self, user_id, limit=100):
        try:
            with open(self.log_file, 'r') as f:
                logs = json.load(f)
            
            user_logs = [log for log in logs if log.get('user_id') == user_id]
            return user_logs[-limit:] 
        except Exception as e:
            print(f"Error reading audit log: {e}")
            return []
    
    def get_recent_actions(self, limit=100):
        try:
            with open(self.log_file, 'r') as f:
                logs = json.load(f)
            
            return logs[-limit:] 
        except Exception as e:
            print(f"Error reading audit log: {e}")
            return []
    
    def search_logs(self, action_type=None, user_id=None, start_date=None, end_date=None):
        try:
            with open(self.log_file, 'r') as f:
                logs = json.load(f)
            
            filtered_logs = logs
            
            if action_type:
                filtered_logs = [log for log in filtered_logs if log.get('action_type') == action_type]
            
            if user_id:
                filtered_logs = [log for log in filtered_logs if log.get('user_id') == user_id]
            
            if start_date:
                filtered_logs = [log for log in filtered_logs if log.get('timestamp') >= start_date]
            
            if end_date:
                filtered_logs = [log for log in filtered_logs if log.get('timestamp') <= end_date]
            
            return filtered_logs
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

audit_logger = AuditLogger()