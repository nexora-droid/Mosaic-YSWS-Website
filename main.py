# DONT DIRECTLY RUN THIS FILE AS IT USES GUNICORN AND IS NOT IDEAL FOR DEVELOPEMNT EDIT maindev.py AND MAKE CHANGES AND THEN WHEN IT'S DONE COPY CHANGES IN THIS FILE (MAIN PRODUCTION FILE)
import os
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, request, render_template, redirect, session, jsonify
from datetime import datetime, timezone, timedelta
import requests
from audit_logger import audit_logger, ActionTypes
from db_init import db_manager
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(
	app.wsgi_app,
	x_for=1,
	x_proto=1,
	x_host=1,
	x_port=1
)
app.secret_key = os.getenv("SECRET_KEY")

app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'mosaic_session'

#inti logger
logger = audit_logger(db_manager)

HACKATIME_API_KEY = os.getenv("HACKATIME_API_KEY")
HACKATIME_BASE_URL = "https://hackatime.hackclub.com/api/v1"

HACKCLUB_CLIENT_ID = os.getenv("HACKCLUB_CLIENT_ID")
HACKCLUB_CLIENT_SECRET = os.getenv("HACKCLUB_CLIENT_SECRET")
HACKCLUB_AUTH_BASE = "https://auth.hackclub.com"

ADMIN_SLACK_IDS = [
    slack_id.strip() 
    for slack_id in os.getenv("ADMIN_SLACK_IDS", "").split(",") 
    if slack_id.strip()
]

if not ADMIN_SLACK_IDS:
    print("WARNING: No admin Slack IDs configured!")

if not HACKATIME_API_KEY:
    print("WARNING: HACKATIME API KEY NOT WORKING!")

if not HACKCLUB_CLIENT_ID or not HACKCLUB_CLIENT_SECRET:
    print("WARNING: Hack Club OAuth credentials not configured!")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Unauthorized - Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Unauthorized - Login required'}), 401
        
        user = get_user_by_id(user_id)
        if not user or not is_admin(user):
            logger.log_action(
                action_type=ActionTypes.UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT,
                user_id=user_id,
                user_name=user.get('name') if user else 'Unknown',
                details={
                    'endpoint': request.endpoint,
                    'method': request.method,
                    'ip': request.remote_addr,
                    'path': request.path
                }
            )
            return jsonify({'error': 'Forbidden - Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def make_session_permanent():
    session.permanent = True
    if 'user_id' in session:
        session.modified = True

#admin rotues api blocked for other users
@app.before_request
def protect_admin_routes():
    if request.path.startswith('/admin') and not request.path.startswith('/admin/api'):
        user_id = session.get('user_id')
        if not user_id:
            return redirect('/signin')
        user = get_user_by_id(user_id)
        if not user or not is_admin(user):
            logger.log_action(
                action_type=ActionTypes.UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT,
                user_id=user_id,
                user_name=user.get('name') if user else 'Unknown',
                details={'path': request.path, 'method': request.method}
            )
            return redirect('/dashboard')

def autoconnectHackatime():
    return {"Authorization": f"Bearer {HACKATIME_API_KEY}"}

def is_admin(user):
    if not user:
        return False
    
    # Must have slack_id in admin list AND role must be Admin
    slack_id_valid = user.get('slack_id') in ADMIN_SLACK_IDS
    role_valid = user.get('role') == 'Admin'
    return slack_id_valid and role_valid

@app.context_processor
def utility_processor():
    return dict(is_admin=is_admin)

def get_user_by_id(user_id):
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_slack_id(slack_id):
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE slack_id = ? LIMIT 1', (slack_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_identity_id(identity_id):
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE identity_id = ? LIMIT 1', (identity_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def validate_project_name(name):
    if not name or not name.strip():
        return False, "Project name cannot be empty"
    if len(name) > 100:
        return False, "Project name too long"
    #no xss
    dangerous_chars = ['<', '>', '"', "'"]
    if any(char in name for char in dangerous_chars):
        return False, "Invalid characters in project name"
    return True, ""

@app.route("/")
def main():
    return render_template('index.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    redirect_uri = f"{request.scheme}://{request.host}/hackclub/callback" # remove hardcoded redirect url form the .env too
    auth_url = (
        f"{HACKCLUB_AUTH_BASE}/oauth/authorize?"
        f"client_id={HACKCLUB_CLIENT_ID}&"
        f"redirect_uri={redirect_uri}&" 
        f"response_type=code&"
        f"scope=openid profile email name slack_id verification_status"
    )
    return render_template('signin.html', hackclub_auth_url=auth_url)

@app.route('/hackclub/callback', methods=['GET'])
def hackclub_callback():
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        return f"Authorization failed: {error}", 400
    
    if not code:
        return "No authorization code received from Hack Club Auth", 400
    
    token_payload = {
        "client_id": HACKCLUB_CLIENT_ID,
        "client_secret": HACKCLUB_CLIENT_SECRET,
        "redirect_uri": f"{request.scheme}://{request.host}/hackclub/callback",
        "code": code,
        "grant_type": "authorization_code"
    }
    
    try:
        token_response = requests.post(
            f"{HACKCLUB_AUTH_BASE}/oauth/token",
            data=token_payload, 
            headers={"Content-Type": "application/x-www-form-urlencoded"}  
        )
        token_data = token_response.json()
        
        if not token_response.ok:
            return f"Token exchange failed: {token_data.get('error', 'Unknown error')}", 400
        
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        
        identity_response = requests.get(
            f"{HACKCLUB_AUTH_BASE}/api/v1/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if not identity_response.ok:
            return "Failed to fetch user identity", 400
        
        identity_data = identity_response.json()
        user_identity = identity_data.get("identity", {})
        
        identity_id = user_identity.get("id")
        slack_id = user_identity.get("slack_id")
        first_name = user_identity.get("first_name")
        last_name = user_identity.get("last_name")
        email = user_identity.get("primary_email")
        verification_status = user_identity.get("verification_status")
        
        user = get_user_by_identity_id(identity_id)
        is_new_user = user is None
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        if not user:
            user_id = db_manager.generate_id()
            role = 'Admin' if slack_id in ADMIN_SLACK_IDS else 'User'
            
            cursor.execute('''
                INSERT INTO users 
                (id, identity_id, slack_id, name, first_name, last_name, email,
                 verification_status, role, date_created, access_token, refresh_token, tiles_balance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id, identity_id, slack_id,
                f"{first_name} {last_name}" if first_name and last_name else None,
                first_name, last_name, email, verification_status, role,
                datetime.now(timezone.utc).isoformat(),
                access_token, refresh_token, 0
            ))
        else:
            user_id = user['id']
            cursor.execute('''
                UPDATE users SET
                    access_token = ?,
                    refresh_token = ?,
                    slack_id = ?,
                    name = ?,
                    first_name = ?,
                    last_name = ?,
                    email = ?,
                    verification_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (
                access_token, refresh_token, slack_id,
                f"{first_name} {last_name}" if first_name and last_name else user.get('name'),
                first_name, last_name, email, verification_status, user_id
            ))
        
        conn.commit()
        conn.close()
        
        user = get_user_by_id(user_id)
        session['user_id'] = user_id
        logger.log_action(
            action_type=ActionTypes.USER_LOGIN,
            user_id=user_id,
            user_name=user.get('name'),
            details={
                'slack_id': slack_id,
                'email': email,
                'is_new_user': is_new_user,
                'verification_status': verification_status
            }
        )
        if is_admin(user):
            return redirect('/admin/dashboard')
        return redirect('/dashboard')
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return f"Authentication failed: {str(e)}", 500

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    if not user:
        return redirect("/signin")
    
    auto_connected = user.get('slack_id') is not None
    projects = []
    
    if auto_connected:
        try:
            url = f"{HACKATIME_BASE_URL}/users/{user['slack_id']}/stats?features=projects&&limit=1000&features=projects&start_date=2025-12-23"
            headers = autoconnectHackatime()
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                raw_projects = data.get("data", {}).get('projects', [])
                if isinstance(raw_projects, list):
                    projects = [{
                        'name': proj.get('name'),
                        'total_seconds': proj.get('total_seconds', 0),
                        'detail': proj.get('description', '')
                    } for proj in raw_projects]
        except Exception as e:
            print(f"Error Fetching Hackatime Projects {e}")
    
    #get saved proj
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE user_id = ?', (user_id,))
    saved_projects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    stats = get_user_stats(user)
    
    return render_template(
        "dashboard.html",
        user=user,
        auto_connected=auto_connected,
        projects=projects,
        saved_projects=saved_projects,
        stats=stats
    )

def get_user_stats(user):
    stats = {
        'total_hours': 0,
        'completed_projects': 0,
        'in_review_projects': 0
    }
    
    if not user.get('slack_id'):
        return stats
    
    try:
        headers = autoconnectHackatime()
        url = f"{HACKATIME_BASE_URL}/users/{user['slack_id']}/stats"
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            stats['total_hours'] = round(data.get('data', {}).get('total_seconds', 0) / 3600, 2)
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM projects WHERE user_id = ? AND status = ?', 
                      (user['id'], 'approved'))
        stats['completed_projects'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) as count FROM projects WHERE user_id = ? AND status = ?', 
                      (user['id'], 'in_review'))
        stats['in_review_projects'] = cursor.fetchone()['count']
        
        conn.close()
        
    except Exception as e:
        print(f"Error Fetching user stats: {e}")
    
    return stats

@app.route("/api/add-project", methods=['POST'])
@login_required
def add_project_api():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    name = data.get('name')
    detail = data.get('detail')
    hackatime_project = data.get('hack_project')
    
    #input validation
    is_valid, error_msg = validate_project_name(name)
    if not is_valid:
        return jsonify({'error': error_msg}), 400
    
    project_id = db_manager.generate_id()
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects 
        (id, user_id, name, detail, hackatime_project, status, created_at,
         total_seconds, approved_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        project_id, user_id, name, detail, hackatime_project, 'draft',
        datetime.now(timezone.utc).isoformat(), 0, 0.0
    ))
    conn.commit()
    conn.close()
    
    logger.log_action(
        action_type=ActionTypes.PROJECT_CREATE,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'project_id': project_id,
            'project_name': name,
            'hackatime_project': hackatime_project,
            'detail': detail
        }
    )
    
    return jsonify({
        'id': project_id,
        'name': name,
        'detail': detail,
        'hackatime_project': hackatime_project,
        'status': 'draft'
    }), 201

@app.route("/api/submit-project/<project_id>", methods=['POST'])
@login_required
def submit_project(project_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    project_row = cursor.fetchone()
    
    if not project_row:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    project = dict(project_row)
    
    if project.get('user_id') != user_id:
        conn.close()
        logger.log_action(
            action_type=ActionTypes.UNAUTHORIZED_ACCESS_ATTEMPT,
            user_id=user_id,
            user_name=user.get('name'),
            details={'project_id': project_id, 'action': 'submit_project'}
        )
        return jsonify({'error': 'Forbidden - Not your project'}), 403
    
    data = request.get_json()
    
    assigned_admin_id = None
    if ADMIN_SLACK_IDS:
        main_admin = get_user_by_slack_id(ADMIN_SLACK_IDS[0])
        if main_admin:
            assigned_admin_id = main_admin['id']
    
    cursor.execute('''
        UPDATE projects SET
            screenshot_url = ?,
            github_url = ?,
            demo_url = ?,
            summary = ?,
            languages = ?,
            status = ?,
            submitted_at = ?,
            assigned_admin_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        data.get('screenshot_url'),
        data.get('github_url'),
        data.get('demo_url'),
        data.get('summary'),
        data.get('languages'),
        'in_review',
        datetime.now(timezone.utc).isoformat(),
        assigned_admin_id,
        project_id
    ))
    
    conn.commit()
    conn.close()
    
    logger.log_action(
        action_type=ActionTypes.PROJECT_SUBMIT,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'project_id': project_id,
            'project_name': project.get('name'),
            'github_url': data.get('github_url'),
            'demo_url': data.get('demo_url'),
            'languages': data.get('languages')
        }
    )
    
    return jsonify({'message': 'Project submitted for review'}), 200

@app.route('/api/delete-project/<project_id>', methods=['DELETE'])
@login_required
def delete_project(project_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    project_row = cursor.fetchone()
    
    if not project_row:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    project = dict(project_row)
    
    is_owner = project.get('user_id') == user_id
    is_admin_user = is_admin(user)
    
    if not is_owner and not is_admin_user:
        conn.close()
        logger.log_action(
            action_type=ActionTypes.UNAUTHORIZED_DELETE_ATTEMPT,
            user_id=user_id,
            user_name=user.get('name'),
            details={
                'project_id': project_id,
                'actual_owner': project.get('user_id'),
                'project_status': project.get('status')
            }
        )
        return jsonify({'error': 'Forbidden - Not your project'}), 403
    
    if not is_admin_user and project.get('status') != 'draft':
        conn.close()
        return jsonify({'error': 'Only draft projects can be deleted'}), 403
    
    try:
        logger.log_action(
            action_type=ActionTypes.PROJECT_DELETE,
            user_id=user_id,
            user_name=user.get('name'),
            details={
                'project_id': project_id,
                'project_name': project.get('name'),
                'project_status': project.get('status'),
                'was_admin_delete': is_admin_user,
                'approved_hours': project.get('approved_hours', 0)
            }
        )
        
        cursor.execute('DELETE FROM project_comments WHERE project_id = ?', (project_id,))
        cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Project deleted successfully'}), 200
    except Exception as e:
        conn.close()
        print(f"Error deleting project: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route("/api/project-details/<project_id>", methods=['GET'])
@login_required
def get_project_details(project_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    project_row = cursor.fetchone()
    
    if not project_row:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    project = dict(project_row)
    
    # STRICT access control
    is_owner = project.get('user_id') == user_id
    is_admin_user = is_admin(user)
    
    if not is_owner and not is_admin_user:
        conn.close()
        logger.log_action(
            action_type=ActionTypes.UNAUTHORIZED_ACCESS_ATTEMPT,
            user_id=user_id,
            user_name=user.get('name'),
            details={
                'project_id': project_id,
                'owner': project.get('user_id'),
                'action': 'view_project_details'
            }
        )
        return jsonify({'error': 'Forbidden - Not your project'}), 403
    
    project_owner = get_user_by_id(project['user_id'])
    project_owner_name = project_owner.get('name') if project_owner else 'Unknown User'

    raw_hours = 0
    if project.get('hackatime_project'):
        project_user = get_user_by_id(project['user_id'])
        if project_user and project_user.get('slack_id'):
            try:
                url = f"{HACKATIME_BASE_URL}/users/{project_user['slack_id']}/stats?features=projects"
                headers = autoconnectHackatime()
                response = requests.get(url, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    raw_projects = data.get("data", {}).get('projects', [])
                    for proj in raw_projects:
                        if proj.get('name') == project['hackatime_project']:
                            raw_hours = round(proj.get('total_seconds', 0) / 3600, 2)
                            break
            except Exception as e:
                print(f"Error Fetching Hackatime Projects {e}")
    
    cursor.execute('SELECT * FROM project_comments WHERE project_id = ?', (project_id,))
    comments = []
    for comment_row in cursor.fetchall():
        comment = dict(comment_row)
        admin = get_user_by_id(comment['admin_id'])
        comments.append({
            'admin_name': admin.get('name') if admin else 'Admin',
            'comment': comment['comment'],
            'created_at': comment.get('created_at')
        })
    
    conn.close()
    return jsonify({
        'id': project['id'],
        'name': project.get('name'),
        'detail': project.get('detail'),
        'hackatime_project': project.get('hackatime_project'),
        'status': project.get('status'),
        'raw_hours': raw_hours,
        'approved_hours': project.get('approved_hours', 0),
        'screenshot_url': project.get('screenshot_url'),
        'github_url': project.get('github_url'),
        'demo_url': project.get('demo_url'),
        'summary': project.get('summary'),
        'languages': project.get('languages'),
        'theme': project.get('theme'),
        'submitted_at': project.get('submitted_at'),
        'reviewed_at': project.get('reviewed_at'),
        'comments': comments,
        'user_name': project_owner_name
    }), 200

@app.route('/api/project-hours', methods=['GET'])
@login_required
def get_project_hours():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    if not user or not user.get('slack_id'):
        return jsonify({'hours': 0, 'message': 'Not connected to Hackatime'}), 200
    
    project_name = request.args.get('project-name') or request.args.get('project_name')
    if not project_name:
        return jsonify({'hours': 0, 'message': 'No project name provided'}), 200
    
    try:
        url = f'{HACKATIME_BASE_URL}/users/{user["slack_id"]}/stats?features=projects'
        headers = autoconnectHackatime()
        response = requests.get(url=url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            raw_projects = data.get("data", {}).get('projects', [])
            for proj in raw_projects:
                if proj.get('name') == project_name:
                    hours = proj.get('total_seconds', 0) / 3600
                    return jsonify({'hours': round(hours, 2)}), 200
            return jsonify({'hours': 0, 'message': 'Project not found'}), 200
        else:
            return jsonify({'hours': 0, 'message': 'Could not fetch from Hackatime'}), 200
    except Exception as e:
        print(f"Error fetching hours: {e}")
        return jsonify({'hours': 0, 'message': 'Error fetching hours'}), 200

@app.route('/leaderboard')
def leaderboard():
    user_id = session.get('user_id')
    user = None
    if user_id:
        user = get_user_by_id(user_id)
    
    users_data = []
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users')
    all_users = [dict(row) for row in cursor.fetchall()]
    
    for u in all_users:
        cursor.execute('''
            SELECT COUNT(*) as count, SUM(approved_hours) as total_hours 
            FROM projects 
            WHERE user_id = ? AND status = ?
        ''', (u['id'], 'approved'))
        
        result = cursor.fetchone()
        projects_count = result['count']
        total_hours = result['total_hours'] or 0
        
        if total_hours > 0:
            users_data.append({
                'name': u.get('name') or f'User #{u["id"]}',
                'total_hours': round(total_hours, 2),
                'projects_count': projects_count,
                'tiles': u.get('tiles_balance', 0)
            })
    
    conn.close()
    
    users_data.sort(key=lambda x: x['total_hours'], reverse=True)
    
    return render_template('leaderboard.html', leaderboard=users_data, user=user)

@app.route('/market')
@login_required
def shop():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    return render_template('soon.html', user=user)

@app.route('/api/themes', methods=['GET'])
@login_required
def get_themes():
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM themes WHERE is_active = 1')
    themes = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({'themes': themes}), 200

@app.route("/faq")
def faq():
    return render_template("faq.html")

@app.route('/api/health')
def health():
    return "OK", 200

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    return render_template('admin_dashboard.html', user=user)

@app.route('/api/all-users', methods=['GET'])
@admin_required
def get_all_users():
    try:
        filter_type = request.args.get('filter', 'all')
        users_list = []
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users')
        all_users = [dict(row) for row in cursor.fetchall()]
        
        for u in all_users:
            cursor.execute('SELECT * FROM projects WHERE user_id = ?', (u['id'],))
            all_projects = [dict(row) for row in cursor.fetchall()]
            
            draft_count = sum(1 for p in all_projects if p.get('status') == 'draft')
            in_review_count = sum(1 for p in all_projects if p.get('status') == 'in_review')
            approved_count = sum(1 for p in all_projects if p.get('status') == 'approved')
            rejected_count = sum(1 for p in all_projects if p.get('status') == 'rejected')
            
            total_hours = sum(p.get('approved_hours', 0) for p in all_projects if p.get('status') == 'approved')
            
            if filter_type == 'with_draft' and draft_count == 0:
                continue
            elif filter_type == 'with_completed' and (in_review_count == 0 and approved_count == 0):
                continue
            
            users_list.append({
                'id': u['id'],
                'name': u.get('name'),
                'email': u.get('email'),
                'tiles_balance': u.get('tiles_balance', 0),
                'total_projects': len(all_projects),
                'draft_count': draft_count,
                'in_review_count': in_review_count,
                'approved_count': approved_count,
                'rejected_count': rejected_count,
                'total_hours': total_hours,
                'raw_hours': 0
            })
        
        conn.close()
        return jsonify({'users': users_list}), 200
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/admin-stats', methods=['GET'])
@admin_required
def get_admin_stats():
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count, SUM(tiles_balance) as total_tiles FROM users')
        user_stats = cursor.fetchone()
        total_users = user_stats['count']
        total_tiles_awarded = user_stats['total_tiles'] or 0
        cursor.execute('SELECT COUNT(DISTINCT user_id) as count FROM projects')
        active_users = cursor.fetchone()['count']
        
        cursor.execute('SELECT * FROM projects')
        all_projects = [dict(row) for row in cursor.fetchall()]
        
        draft_count = 0
        in_review_count = 0
        approved_count = 0
        rejected_count = 0
        total_approved_hours = 0
        total_raw_hours = 0
        user_hackatime_cache = {}
        
        for project in all_projects:
            status = project.get('status')
            approved_hours = project.get('approved_hours', 0)
            
            if status == 'draft':
                draft_count += 1
            elif status == 'in_review':
                in_review_count += 1
            elif status == 'approved':
                approved_count += 1
                total_approved_hours += approved_hours
            elif status == 'rejected':
                rejected_count += 1
            
            hackatime_project_name = project.get('hackatime_project')
            if hackatime_project_name:
                user_id = project.get('user_id')
                if user_id not in user_hackatime_cache:
                    project_user = get_user_by_id(user_id)
                    if project_user and project_user.get('slack_id'):
                        try:
                            url = f"{HACKATIME_BASE_URL}/users/{project_user['slack_id']}/stats?features=projects"
                            headers = autoconnectHackatime()
                            response = requests.get(url, headers=headers, timeout=5)
                            
                            if response.status_code == 200:
                                data = response.json()
                                user_hackatime_cache[user_id] = data.get("data", {}).get('projects', [])
                            else:
                                user_hackatime_cache[user_id] = []
                        except Exception as e:
                            print(f"Error fetching Hackatime for user {user_id}: {e}")
                            user_hackatime_cache[user_id] = []
                    else:
                        user_hackatime_cache[user_id] = []
                
                for hackatime_proj in user_hackatime_cache.get(user_id, []):
                    if hackatime_proj.get('name') == hackatime_project_name:
                        raw_hours = hackatime_proj.get('total_seconds', 0) / 3600
                        total_raw_hours += raw_hours
                        break
        
        conn.close()
        
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'total_projects': len(all_projects),
            'draft_projects': draft_count,
            'pending_reviews': in_review_count,
            'approved_projects': approved_count,
            'rejected_projects': rejected_count,
            'total_hours': round(total_approved_hours, 2),
            'raw_hours': round(total_raw_hours, 2),
            'total_tiles_awarded': total_tiles_awarded
        }), 200
    except Exception as e:
        print(f"Error fetching admin stats: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/user-projects/<user_id>', methods=['GET'])
@admin_required
def get_user_projects(user_id):
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM projects WHERE user_id = ?', (user_id,))
        projects = [dict(row) for row in cursor.fetchall()]
        
        user = get_user_by_id(user_id)
        hackatime_projects = {}
        total_raw_hours = 0
        
        if user and user.get('slack_id'):
            try:
                url = f"{HACKATIME_BASE_URL}/users/{user['slack_id']}/stats?features=projects"
                headers = autoconnectHackatime()
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    raw_projects = data.get("data", {}).get('projects', [])
                    for proj in raw_projects:
                        hackatime_projects[proj.get('name')] = proj.get('total_seconds', 0) / 3600
            except Exception as e:
                print(f"Error fetching Hackatime data for user {user_id}: {e}")
        
        for proj in projects:
            hackatime_name = proj.get('hackatime_project')
            if hackatime_name and hackatime_name in hackatime_projects:
                proj['raw_hours'] = round(hackatime_projects[hackatime_name], 2)
                total_raw_hours += hackatime_projects[hackatime_name]
            else:
                proj['raw_hours'] = 0
        
        projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        conn.close()
        
        return jsonify({
            'projects': projects,
            'total_raw_hours': round(total_raw_hours, 2),
            'user_name': user.get('name') if user else 'Unknown',
            'user_slack_id': user.get('slack_id') if user else None
        }), 200
    except Exception as e:
        print(f"Error fetching user projects: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/projects-by-status/<status>', methods=['GET'])
@admin_required
def get_projects_by_status(status):
    try:
        if status not in ['draft', 'in_review', 'approved', 'rejected']:
            return jsonify({'error': 'Invalid status'}), 400
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                p.*,
                u.name as user_name,
                u.slack_id as user_slack_id
            FROM projects p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.status = ?
            ORDER BY p.submitted_at DESC, p.created_at DESC
        ''', (status,))
        
        projects = [dict(row) for row in cursor.fetchall()]
        
        slack_id_to_hackatime = {}
        
        for project in projects:
            slack_id = project.get('user_slack_id')
            hackatime_project = project.get('hackatime_project')
            
            if slack_id and hackatime_project:
                if slack_id not in slack_id_to_hackatime:
                    try:
                        url = f"{HACKATIME_BASE_URL}/users/{slack_id}/stats?features=projects"
                        headers = autoconnectHackatime()
                        response = requests.get(url, headers=headers, timeout=5)
                        
                        if response.status_code == 200:
                            data = response.json()
                            slack_id_to_hackatime[slack_id] = data.get("data", {}).get('projects', [])
                        else:
                            slack_id_to_hackatime[slack_id] = []
                    except Exception as e:
                        print(f"Error fetching Hackatime for {slack_id}: {e}")
                        slack_id_to_hackatime[slack_id] = []
                
                project['raw_hours'] = 0
                for hackatime_proj in slack_id_to_hackatime.get(slack_id, []):
                    if hackatime_proj.get('name') == hackatime_project:
                        project['raw_hours'] = round(hackatime_proj.get('total_seconds', 0) / 3600, 2)
                        break
            else:
                project['raw_hours'] = 0
        
        conn.close()
        
        return jsonify({'projects': projects}), 200
        
    except Exception as e:
        print(f"Error fetching projects by status: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/api/review-project/<project_id>', methods=['POST'])
@admin_required
def admin_review_project(project_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    project_row = cursor.fetchone()
    
    if not project_row:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    project = dict(project_row)
    data = request.get_json()
    
    old_status = project.get('status')
    new_status = data.get('status')
    old_hours = project.get('approved_hours', 0)
    new_hours = float(data.get('approved_hours', 0))
    
    cursor.execute('''
        UPDATE projects SET
            status = ?,
            approved_hours = ?,
            reviewed_at = ?,
            theme = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        new_status,
        new_hours,
        datetime.now(timezone.utc).isoformat(),
        data.get('theme'),
        project_id
    ))
    
    conn.commit()
    conn.close()
    
    action_type = ActionTypes.ADMIN_REVIEW_PROJECT
    if new_status == 'approved':
        action_type = ActionTypes.ADMIN_APPROVE_PROJECT
    elif new_status == 'rejected':
        action_type = ActionTypes.ADMIN_REJECT_PROJECT
    
    logger.log_action(
        action_type=action_type,
        user_id=user_id,
        user_name=user.get('name'),
        target_user_id=project.get('user_id'),
        details={
            'project_id': project_id,
            'project_name': project.get('name'),
            'old_status': old_status,
            'new_status': new_status,
            'old_hours': old_hours,
            'new_hours': new_hours,
            'theme': data.get('theme'),
            'hours_changed': new_hours != old_hours
        }
    )
    
    return jsonify({'message': 'Project review updated'}), 200

@app.route('/admin/api/comment-project/<project_id>', methods=['POST'])
@admin_required
def admin_comment_project(project_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    project_row = cursor.fetchone()
    
    if not project_row:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    project = dict(project_row)
    data = request.get_json()
    comment_text = data.get('comment')
    if not comment_text:
        conn.close()
        return jsonify({'error': 'Comment cannot be empty'}), 400
    
    comment_id = db_manager.generate_id()
    
    cursor.execute('''
        INSERT INTO project_comments 
        (id, project_id, admin_id, comment, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        comment_id,
        project_id,
        user_id,
        comment_text,
        datetime.now(timezone.utc).isoformat()
    ))
    
    conn.commit()
    conn.close()
    
    logger.log_action(
        action_type=ActionTypes.ADMIN_COMMENT_PROJECT,
        user_id=user_id,
        user_name=user.get('name'),
        target_user_id=project.get('user_id'),
        details={
            'project_id': project_id,
            'project_name': project.get('name'),
            'comment_length': len(comment_text),
            'comment_preview': comment_text[:100]
        }
    )
    
    return jsonify({'message': 'Comment added'}), 201

@app.route('/admin/api/assign-project/<project_id>', methods=['POST'])
@admin_required
def admin_assign_project(project_id):
    user_id = session.get('user_id')
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM projects WHERE id = ?', (project_id,))
    
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    cursor.execute('''
        UPDATE projects SET assigned_admin_id = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (user_id, project_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Project assigned successfully'}), 200

@app.route('/admin/api/award-tiles/<project_id>', methods=['POST'])
@admin_required
def admin_award_tiles(project_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
    project_row = cursor.fetchone()
    
    if not project_row:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    project = dict(project_row)
    data = request.get_json()
    tiles_amount = int(data.get('tiles', 0))
    
    if tiles_amount <= 0:
        conn.close()
        return jsonify({'error': 'Invalid tiles amount'}), 400
    
    project_user_id = project['user_id']
    cursor.execute('SELECT tiles_balance FROM users WHERE id = ?', (project_user_id,))
    user_row = cursor.fetchone()
    
    current_balance = user_row['tiles_balance'] if user_row else 0
    new_balance = current_balance + tiles_amount
    
    cursor.execute('''
        UPDATE users SET tiles_balance = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (new_balance, project_user_id))
    
    conn.commit()
    conn.close()
    
    project_user = get_user_by_id(project_user_id)
    
    logger.log_action(
        action_type=ActionTypes.ADMIN_AWARD_TILES,
        user_id=user_id,
        user_name=user.get('name'),
        target_user_id=project_user_id,
        details={
            'project_id': project_id,
            'project_name': project.get('name'),
            'tiles_awarded': tiles_amount,
            'old_balance': current_balance,
            'new_balance': new_balance,
            'recipient_name': project_user.get('name') if project_user else 'Unknown'
        }
    )
    
    return jsonify({
        'message': 'Tiles awarded successfully',
        'new_balance': new_balance
    }), 200

@app.route('/admin/api/add-theme', methods=['POST'])
@admin_required
def admin_add_theme():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    data = request.get_json()
    theme_name = data.get('name')
    theme_description = data.get('description', '')
    
    if not theme_name:
        return jsonify({'error': 'Theme name is required'}), 400
    
    theme_id = db_manager.generate_id()
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO themes (id, name, description, is_active, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        theme_id,
        theme_name,
        theme_description,
        1,
        datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    conn.close()
    
    logger.log_action(
        action_type=ActionTypes.ADMIN_CREATE_THEME,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'theme_id': theme_id,
            'theme_name': theme_name,
            'theme_description': theme_description
        }
    )
    
    return jsonify({
        'message': 'Theme added successfully',
        'theme': {
            'id': theme_id,
            'name': theme_name,
            'description': theme_description
        }
    }), 201

@app.route('/admin/api/delete-theme/<theme_id>', methods=['DELETE'])
@admin_required
def admin_delete_theme(theme_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM themes WHERE id = ?', (theme_id,))
    theme_row = cursor.fetchone()
    
    if not theme_row:
        conn.close()
        return jsonify({'error': 'Theme not found'}), 404
    
    theme = dict(theme_row)
    
    cursor.execute('''
        UPDATE themes SET is_active = 0, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (theme_id,))
    conn.commit()
    conn.close()
    
    logger.log_action(
        action_type=ActionTypes.ADMIN_DELETE_THEME,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'theme_id': theme_id,
            'theme_name': theme.get('name')
        }
    )
    
    return jsonify({'message': 'Theme deleted successfully'}), 200

@app.route('/admin/audit-logs')
@admin_required
def admin_audit_logs():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    return render_template('admin_audit_logs.html', user=user)

@app.route('/api/admin/audit-logs', methods=['GET'])
@admin_required
def get_audit_logs():
    limit = int(request.args.get('limit', 100))
    action_type = request.args.get('action_type')
    filter_user_id = request.args.get('user_id')
    
    try:
        if filter_user_id:
            logs = logger.get_user_actions(filter_user_id, limit)
        elif action_type:
            logs = logger.search_logs(action_type=action_type)[-limit:]
        else:
            logs = logger.get_recent_actions(limit)
        
        return jsonify({'logs': logs}), 200
    except Exception as e:
        print(f"Error fetching audit logs: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/admin/fraud-detection', methods=['GET'])
@admin_required
def fraud_detection():
    try:
        all_logs = logger.get_recent_actions(2000)
        suspicious_activities = []
        
        user_action_counts = {}
        user_recent_actions = {}
        user_first_seen = {}
        
        for log in all_logs:
            log_user_id = log.get('user_id')
            action_type = log.get('action_type')
            timestamp = log.get('timestamp')
            
            if not log_user_id:
                continue
            
            if log_user_id not in user_action_counts:
                user_action_counts[log_user_id] = {}
                user_recent_actions[log_user_id] = []
                user_first_seen[log_user_id] = timestamp
            
            if action_type not in user_action_counts[log_user_id]:
                user_action_counts[log_user_id][action_type] = 0
            
            user_action_counts[log_user_id][action_type] += 1
            user_recent_actions[log_user_id].append({
                'action': action_type,
                'timestamp': timestamp
            })
        
        for uid, actions in user_action_counts.items():
            delete_count = actions.get('PROJECT_DELETE', 0)
            if delete_count > 5:
                user_info = get_user_by_id(uid)
                recent_deletes = [a for a in user_recent_actions[uid] if a['action'] == 'PROJECT_DELETE']
                latest_timestamp = recent_deletes[-1]['timestamp'] if recent_deletes else None
                
                suspicious_activities.append({
                    'user_id': uid,
                    'user_name': user_info.get('name') if user_info else 'Unknown',
                    'type': 'EXCESSIVE_DELETIONS',
                    'count': delete_count,
                    'severity': 'HIGH',
                    'description': f'Deleted {delete_count} projects (threshold: 5)',
                    'timestamp': latest_timestamp
                })
        
        for uid, actions in user_action_counts.items():
            create_count = actions.get('PROJECT_CREATE', 0)
            if create_count > 15:
                user_info = get_user_by_id(uid)
                recent_creates = [a for a in user_recent_actions[uid] if a['action'] == 'PROJECT_CREATE']
                latest_timestamp = recent_creates[-1]['timestamp'] if recent_creates else None
                
                suspicious_activities.append({
                    'user_id': uid,
                    'user_name': user_info.get('name') if user_info else 'Unknown',
                    'type': 'EXCESSIVE_CREATIONS',
                    'count': create_count,
                    'severity': 'MEDIUM',
                    'description': f'Created {create_count} projects (threshold: 15)',
                    'timestamp': latest_timestamp
                })
        
        for uid, recent_actions in user_recent_actions.items():
            if len(recent_actions) >= 10:
                recent_10 = recent_actions[-10:]
                timestamps = sorted([
                    datetime.fromisoformat(a['timestamp']) 
                    for a in recent_10
                ])
                
                if len(timestamps) > 1:
                    time_span = (timestamps[-1] - timestamps[0]).total_seconds()
                    if 0 < time_span < 60: 
                        user_info = get_user_by_id(uid)
                        suspicious_activities.append({
                            'user_id': uid,
                            'user_name': user_info.get('name') if user_info else 'Unknown',
                            'type': 'RAPID_ACTIONS',
                            'severity': 'MEDIUM',
                            'description': f'10 actions in {time_span:.1f} seconds (bot-like behavior)',
                            'timestamp': recent_10[-1]['timestamp']
                        })
        
        for log in all_logs:
            if log.get('action_type') == 'ADMIN_AWARD_TILES':
                details = log.get('details', {})
                tiles_awarded = details.get('tiles_awarded', 0)
                if tiles_awarded > 500:  
                    suspicious_activities.append({
                        'user_id': log.get('user_id'),
                        'user_name': log.get('user_name'),
                        'type': 'LARGE_TILE_AWARD',
                        'severity': 'HIGH',
                        'description': f'Awarded {tiles_awarded} tiles to {details.get("recipient_name")} (threshold: 500)',
                        'timestamp': log.get('timestamp')
                    })
        
        unauthorized_types = [
            'UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT',
            'UNAUTHORIZED_DELETE_ATTEMPT',
            'UNAUTHORIZED_ACCESS_ATTEMPT'
        ]
        
        unauthorized_by_user = {}
        for log in all_logs:
            if log.get('action_type') in unauthorized_types:
                uid = log.get('user_id')
                if uid:
                    if uid not in unauthorized_by_user:
                        unauthorized_by_user[uid] = []
                    unauthorized_by_user[uid].append(log)
        
        for uid, attempts in unauthorized_by_user.items():
            if len(attempts) > 3: 
                user_info = get_user_by_id(uid)
                suspicious_activities.append({
                    'user_id': uid,
                    'user_name': user_info.get('name') if user_info else 'Unknown',
                    'type': 'MULTIPLE_UNAUTHORIZED_ATTEMPTS',
                    'severity': 'HIGH',
                    'count': len(attempts),
                    'description': f'{len(attempts)} unauthorized access attempts (threshold: 3)',
                    'timestamp': attempts[-1].get('timestamp')
                })
        
        for uid, actions in user_action_counts.items():
            creates = actions.get('PROJECT_CREATE', 0)
            submits = actions.get('PROJECT_SUBMIT', 0)
            
            if creates >= 3 and submits >= 3:
                create_actions = [a for a in user_recent_actions[uid] if a['action'] == 'PROJECT_CREATE']
                submit_actions = [a for a in user_recent_actions[uid] if a['action'] == 'PROJECT_SUBMIT']
                
                if create_actions and submit_actions:
                    create_time = datetime.fromisoformat(create_actions[-1]['timestamp'])
                    submit_time = datetime.fromisoformat(submit_actions[-1]['timestamp'])
                    time_diff = (submit_time - create_time).total_seconds()
                    
                    if 0 < time_diff < 3600:  
                        user_info = get_user_by_id(uid)
                        suspicious_activities.append({
                            'user_id': uid,
                            'user_name': user_info.get('name') if user_info else 'Unknown',
                            'type': 'RAPID_PROJECT_LIFECYCLE',
                            'severity': 'MEDIUM',
                            'description': f'Created and submitted {submits} projects within 1 hour',
                            'timestamp': submit_actions[-1]['timestamp']
                        })
        
        for uid, actions in user_action_counts.items():
            first_seen = user_first_seen.get(uid)
            if first_seen:
                account_age = (datetime.now(timezone.utc) - datetime.fromisoformat(first_seen)).total_seconds()
                total_actions = sum(actions.values())
                
                if account_age < 86400 and total_actions > 20:  
                    user_info = get_user_by_id(uid)
                    suspicious_activities.append({
                        'user_id': uid,
                        'user_name': user_info.get('name') if user_info else 'Unknown',
                        'type': 'NEW_USER_HIGH_ACTIVITY',
                        'severity': 'MEDIUM',
                        'description': f'New account with {total_actions} actions in first 24h',
                        'timestamp': user_recent_actions[uid][-1]['timestamp']
                    })
        
        suspicious_activities.sort(
            key=lambda x: x.get('timestamp', '1970-01-01T00:00:00'), 
            reverse=True
        )
        
        total_unauthorized = sum(len(attempts) for attempts in unauthorized_by_user.values())
        
        return jsonify({
            'suspicious_activities': suspicious_activities,
            'total_logs_analyzed': len(all_logs),
            'unauthorized_attempts': total_unauthorized,
            'detection_timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
        
    except Exception as e:
        print(f"Error in fraud detection: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/admin/user-activity/<user_id>', methods=['GET'])
@admin_required
def get_user_activity_summary(user_id):
    try:
        logs = logger.get_user_actions(user_id, limit=500)
        
        action_summary = {}
        for log in logs:
            action = log.get('action_type')
            if action not in action_summary:
                action_summary[action] = 0
            action_summary[action] += 1
        
        first_activity = logs[0].get('timestamp') if logs else None
        last_activity = logs[-1].get('timestamp') if logs else None
        
        return jsonify({
            'user_id': user_id,
            'total_actions': len(logs),
            'action_summary': action_summary,
            'first_activity': first_activity,
            'last_activity': last_activity,
            'recent_logs': logs[-20:]
        }), 200
        
    except Exception as e:
        print(f"Error getting user activity: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

