import sqlite3
from datetime import datetime, timezone

class DatabaseManager:
    def __init__(self, db_path='mosaic.db'):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                identity_id TEXT UNIQUE,
                slack_id TEXT,
                name TEXT,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                verification_status TEXT,
                role TEXT DEFAULT 'User',
                date_created TEXT NOT NULL,
                hackatime_username TEXT,
                access_token TEXT,
                refresh_token TEXT,
                tiles_balance INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                detail TEXT,
                hackatime_project TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL,
                total_seconds INTEGER DEFAULT 0,
                approved_hours REAL DEFAULT 0.0,
                screenshot_url TEXT,
                github_url TEXT,
                demo_url TEXT,
                summary TEXT,
                languages TEXT,
                theme TEXT,
                submitted_at TEXT,
                reviewed_at TEXT,
                assigned_admin_id TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (assigned_admin_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_comments (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                admin_id TEXT NOT NULL,
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (admin_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                target_user_id TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                session_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (target_user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS themes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_slack_id ON users(slack_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_identity_id ON users(identity_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_project_comments_project_id ON project_comments(project_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type ON audit_logs(action_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_themes_is_active ON themes(is_active)')
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
    
    def generate_id(self):
        import uuid
        return str(uuid.uuid4())

# Initialize database on import
db_manager = DatabaseManager()