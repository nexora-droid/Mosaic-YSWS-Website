from datetime import datetime, timezone
from flask import request, session
import json

class audit_logger:
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def log_action(self, action_type, user_id=None, user_name=None, details=None, target_user_id=None):
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action_type': action_type,
            'user_id': user_id,
            'user_name': user_name,
            'target_user_id': target_user_id,
            'details': json.dumps(details or {}),
            'ip_address': request.remote_addr if request else None,
            'user_agent': request.headers.get('User-Agent') if request else None,
            'session_id': session.get('user_id') if session else None
        }
        
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO audit_logs 
                (timestamp, action_type, user_id, user_name, target_user_id, 
                 details, ip_address, user_agent, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                log_entry['timestamp'],
                log_entry['action_type'],
                log_entry['user_id'],
                log_entry['user_name'],
                log_entry['target_user_id'],
                log_entry['details'],
                log_entry['ip_address'],
                log_entry['user_agent'],
                log_entry['session_id']
            ))
            conn.commit()
            conn.close()
            print(f"[AUDIT LOG] {action_type} by {user_name or user_id}")
        except Exception as e:
            print(f"Error writing to audit log: {e}")
    
    def get_user_actions(self, user_id, limit=100):
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM audit_logs 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (user_id, limit))
            
            logs = []
            for row in cursor.fetchall():
                log_data = dict(row)
                log_data['details'] = json.loads(log_data['details']) if log_data['details'] else {}
                logs.append(log_data)
            
            conn.close()
            return logs
        except Exception as e:
            print(f"Error reading audit log: {e}")
            return []
    
    def get_recent_actions(self, limit=100):
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM audit_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            
            logs = []
            for row in cursor.fetchall():
                log_data = dict(row)
                log_data['details'] = json.loads(log_data['details']) if log_data['details'] else {}
                logs.append(log_data)
            
            conn.close()
            return logs
        except Exception as e:
            print(f"Error reading audit log: {e}")
            return []
    
    def search_logs(self, action_type=None, user_id=None, start_date=None, end_date=None):
        try:
            conn = self.db_manager.get_connection()
            cursor = conn.cursor()
            
            query = "SELECT * FROM audit_logs WHERE 1=1"
            params = []
            
            if action_type:
                query += " AND action_type = ?"
                params.append(action_type)
            
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date)
            
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date)
            
            query += " ORDER BY timestamp DESC LIMIT 500"
            
            cursor.execute(query, params)
            
            logs = []
            for row in cursor.fetchall():
                log_data = dict(row)
                log_data['details'] = json.loads(log_data['details']) if log_data['details'] else {}
                logs.append(log_data)
            
            conn.close()
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
    UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT = 'UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT'
    UNAUTHORIZED_DELETE_ATTEMPT = 'UNAUTHORIZED_DELETE_ATTEMPT'
    UNAUTHORIZED_ACCESS_ATTEMPT = 'UNAUTHORIZED_ACCESS_ATTEMPT'
    SUSPICIOUS_RAPID_ACTIONS = 'SUSPICIOUS_RAPID_ACTIONS'
    SUSPICIOUS_MULTIPLE_DELETES = 'SUSPICIOUS_MULTIPLE_DELETES'
    SUSPICIOUS_TILE_REQUEST = 'SUSPICIOUS_TILE_REQUEST'
    BLOCKED_IP_ACCESS_ATTEMPT = 'BLOCKED_IP_ACCESS_ATTEMPT'

