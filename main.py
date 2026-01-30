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
from werkzeug.utils import secure_filename
from PIL import Image
import uuid
import traceback

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
UPLOAD_FOLDER = 'static/products'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024 

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

#cehck filename
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def optimize_image(image_path, max_size=(800, 800)):
    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            img.save(image_path, 'JPEG', quality=85, optimize=True)
            return True
    except Exception as e:
        print(f"Error optimizing image: {e}")
        return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Unauthorized - Login required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def page_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            session['next_url'] = request.url
            return redirect('/signin')
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
    
    token_url = f"{HACKCLUB_AUTH_BASE}/oauth/token"
    token_response = requests.post(token_url, data=token_payload, timeout=10)
    
    if token_response.status_code != 200:
        return f"Failed to exchange code for token: {token_response.text}", 400
    
    token_data = token_response.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    
    userinfo_url = f"{HACKCLUB_AUTH_BASE}/oauth/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    userinfo_response = requests.get(userinfo_url, headers=headers, timeout=10)
    
    if userinfo_response.status_code != 200:
        return f"Failed to fetch user info: {userinfo_response.text}", 400
    
    user_info = userinfo_response.json()
    
    identity_id = user_info.get("sub")
    slack_id = user_info.get("slack_id")
    name = user_info.get("name")
    email = user_info.get("email")
    verification_status = user_info.get("verification_status")
    
    given_name = user_info.get("given_name", "")
    family_name = user_info.get("family_name", "")
    
    existing_user = get_user_by_identity_id(identity_id)
    
    if existing_user:
        user_id = existing_user['id']
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET
                slack_id = ?,
                name = ?,
                first_name = ?,
                last_name = ?,
                email = ?,
                verification_status = ?,
                access_token = ?,
                refresh_token = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE identity_id = ?
        ''', (
            slack_id,
            name,
            given_name,
            family_name,
            email,
            verification_status,
            access_token,
            refresh_token,
            identity_id
        ))
        conn.commit()
        conn.close()
    else:
        user_id = db_manager.generate_id()
        
        is_admin_user = slack_id in ADMIN_SLACK_IDS
        user_role = 'Admin' if is_admin_user else 'User'
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (
                id, identity_id, slack_id, name, first_name, last_name,
                email, verification_status, role, date_created,
                hackatime_username, access_token, refresh_token, tiles_balance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            identity_id,
            slack_id,
            name,
            given_name,
            family_name,
            email,
            verification_status,
            user_role,
            datetime.now(timezone.utc).isoformat(),
            None,
            access_token,
            refresh_token,
            0
        ))
        conn.commit()
        conn.close()
    
    session['user_id'] = user_id
    session.permanent = True
    
    user = get_user_by_id(user_id)
    
    logger.log_action(
        action_type=ActionTypes.USER_LOGIN,
        user_id=user_id,
        user_name=user.get('name') if user else 'Unknown',
        details={
            'login_method': 'hackclub_oauth',
            'verification_status': verification_status,
            'is_new_user': not existing_user
        }
    )
    
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    user_name = None
    
    if user_id:
        user = get_user_by_id(user_id)
        user_name = user.get('name') if user else 'Unknown'
    
    session.clear()
    
    if user_id:
        logger.log_action(
            action_type=ActionTypes.USER_LOGOUT,
            user_id=user_id,
            user_name=user_name
        )
    
    return redirect('/')

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
            
            #debugging
            print(f"[HACKATIME DEBUG] Fetching projects for slack_id: {user['slack_id']}")
            print(f"[HACKATIME DEBUG] URL: {url}")
            print(f"[HACKATIME DEBUG] API Key present: {bool(HACKATIME_API_KEY)}")
            
            response = requests.get(url, headers=headers, timeout=5)
            
            print(f"[HACKATIME DEBUG] Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                raw_projects = data.get("data", {}).get('projects', [])
                if isinstance(raw_projects, list):
                    projects = [{
                        'name': proj.get('name'),
                        'total_seconds': proj.get('total_seconds', 0),
                        'detail': proj.get('description', '')
                    } for proj in raw_projects]
                    print(f"[HACKATIME DEBUG] Successfully fetched {len(projects)} projects")
            else:
                print(f"[HACKATIME DEBUG] Failed with status {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[HACKATIME ERROR] Error Fetching Hackatime Projects: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[HACKATIME DEBUG] User not connected (no slack_id)")
    
    # Get saved projects
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

@app.route('/api/user/hackatime-projects', methods=['GET'])
@login_required
def get_user_hackatime_projects():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if not user.get('slack_id'):
        return jsonify({'error': 'Slack ID not found for user'}), 400
    
    try:
        url = f"{HACKATIME_BASE_URL}/users/{user['slack_id']}/stats?features=projects"
        headers = autoconnectHackatime()
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return jsonify({'error': f'Failed to fetch Hackatime data: {response.text}'}), response.status_code
        
        data = response.json()
        projects = data.get("data", {}).get('projects', [])
        
        return jsonify({
            'projects': projects,
            'message': 'Projects fetched successfully'
        }), 200
    
    except Exception as e:
        print(f"Error fetching Hackatime projects: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

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
        user_name=user['name'],
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
            user_name=user['name'],
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
        user_name=user['name'],
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
            user_name=user['name'],
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
            user_name=user['name'],
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
            user_name=user['name'],
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
        
        print(f"[PROJECT-HOURS] Fetching for user {user_id}, project: {project_name}")
        
        response = requests.get(url=url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            raw_projects = data.get("data", {}).get('projects', [])
            for proj in raw_projects:
                if proj.get('name') == project_name:
                    hours = proj.get('total_seconds', 0) / 3600
                    print(f"[PROJECT-HOURS] Found project: {hours} hours")
                    return jsonify({'hours': round(hours, 2)}), 200
            print(f"[PROJECT-HOURS] Project not found in Hackatime")
            return jsonify({'hours': 0, 'message': 'Project not found'}), 200
        else:
            print(f"[PROJECT-HOURS] Hackatime API error: {response.status_code}")
            return jsonify({'hours': 0, 'message': 'Could not fetch from Hackatime'}), 200
    except Exception as e:
        print(f"[PROJECT-HOURS ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'hours': 0, 'message': 'Error fetching hours'}), 200


@app.route('/api/projects', methods=['GET'])
@login_required
def get_projects():
    user_id = session.get('user_id')
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    rows = cursor.fetchall()
    
    projects = []
    for row in rows:
        project = dict(row)
        
        cursor.execute('''
            SELECT pc.*, u.name as admin_name 
            FROM project_comments pc
            LEFT JOIN users u ON pc.admin_id = u.id
            WHERE pc.project_id = ?
            ORDER BY pc.created_at ASC
        ''', (project['id'],))
        comments = [dict(comment_row) for comment_row in cursor.fetchall()]
        project['comments'] = comments
        
        projects.append(project)
    
    conn.close()
    
    return jsonify({'projects': projects}), 200

@app.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    data = request.get_json()
    
    project_name = data.get('name', '').strip()
    is_valid, error_message = validate_project_name(project_name)
    if not is_valid:
        return jsonify({'error': error_message}), 400
    
    project_id = db_manager.generate_id()
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO projects 
        (id, user_id, name, detail, hackatime_project, status, created_at, total_seconds)
        VALUES (?, ?, ?, ?, ?, 'draft', ?, 0)
    ''', (
        project_id,
        user_id,
        project_name,
        data.get('detail', ''),
        data.get('hackatime_project'),
        datetime.now(timezone.utc).isoformat()
    ))
    
    conn.commit()
    conn.close()
    
    logger.log_action(
        action_type=ActionTypes.PROJECT_CREATE,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'project_id': project_id,
            'project_name': project_name,
            'hackatime_project': data.get('hackatime_project')
        }
    )
    
    return jsonify({
        'message': 'Project created successfully',
        'project_id': project_id
    }), 201

@app.route('/api/projects/<project_id>', methods=['PUT'])
@login_required
def update_project(project_id):
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    
    conn = db_manager.get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM projects WHERE id = ? AND user_id = ?', (project_id, user_id))
    project_row = cursor.fetchone()
    
    if not project_row:
        conn.close()
        return jsonify({'error': 'Project not found or unauthorized'}), 404
    
    project = dict(project_row)
    
    if project.get('status') in ['approved', 'in_review']:
        conn.close()
        return jsonify({'error': 'Cannot edit project that is in review or approved'}), 403
    
    data = request.get_json()
    
    project_name = data.get('name', project['name']).strip()
    is_valid, error_message = validate_project_name(project_name)
    if not is_valid:
        conn.close()
        return jsonify({'error': error_message}), 400
    
    cursor.execute('''
        UPDATE projects SET
            name = ?,
            detail = ?,
            hackatime_project = ?,
            screenshot_url = ?,
            github_url = ?,
            demo_url = ?,
            summary = ?,
            languages = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        project_name,
        data.get('detail', project['detail']),
        data.get('hackatime_project', project['hackatime_project']),
        data.get('screenshot_url', project['screenshot_url']),
        data.get('github_url', project['github_url']),
        data.get('demo_url', project['demo_url']),
        data.get('summary', project['summary']),
        data.get('languages', project['languages']),
        project_id
    ))
    
    conn.commit()
    conn.close()
    
    logger.log_action(
        action_type=ActionTypes.PROJECT_UPDATE,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'project_id': project_id,
            'project_name': project_name,
            'changes': {
                'name_changed': project_name != project['name'],
                'detail_changed': data.get('detail') != project['detail'],
                'hackatime_project_changed': data.get('hackatime_project') != project['hackatime_project']
            }
        }
    )
    
    return jsonify({'message': 'Project updated successfully'}), 200


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
@page_login_required
def shop():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    return render_template('market.html', user=user, is_admin=is_admin)

@app.route('/admin/market')
@admin_required
def admin_market():
    user_id = session.get('user_id')
    user = get_user_by_id(user_id)
    return render_template('admin_market.html', user=user)

@app.route('/admin/api/market/items', methods=['GET'])
@admin_required
def get_admin_market_items():
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM market_items ORDER BY created_at DESC')
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({'items': items}), 200
    except Exception as e:
        print(f"Error fetching market items: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/market/items', methods=['GET'])
@login_required
def get_market_items():
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM market_items WHERE is_active = 1 ORDER BY created_at DESC')
        items = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({'items': items}), 200
    except Exception as e:
        print(f"Error fetching market items: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/api/market/items', methods=['POST'])
@admin_required
def create_market_item():
    try:
        name = request.form.get('name')
        description = request.form.get('description', '')
        price = request.form.get('price')
        estimated_hours = request.form.get('estimated_hours', 0.0)
        stock_quantity = request.form.get('stock_quantity', -1)
        is_active = request.form.get('is_active', 'true').lower() == 'true'
        
        if not name or not price:
            return jsonify({'error': 'Name and price are required'}), 400
        
        try:
            price = int(price)
            estimated_hours = float(estimated_hours) if estimated_hours else 0.0
            stock_quantity = int(stock_quantity)
        except ValueError:
            return jsonify({'error': 'Invalid numeric values'}), 400
        
        image_url = request.form.get('image_url')

        if not image_url and 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                if not allowed_file(file.filename):
                    return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400

                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)

                if file_size > 5 * 1024 * 1024:
                    return jsonify({'error': 'File size must be less than 5MB'}), 400

                filename = f"{db_manager.generate_id()}.{file.filename.rsplit('.', 1)[1].lower()}"
                filepath = os.path.join('static', 'products', filename)

                try:
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    file.save(filepath)
                    image_url = f'/static/products/{filename}'
                except Exception as e:
                    print(f"Error processing image: {e}")
                    return jsonify({'error': 'Error processing image'}), 400

        
        item_id = db_manager.generate_id()
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO market_items 
            (id, name, description, image_url, price, estimated_hours, stock_quantity, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item_id,
            name,
            description,
            image_url,
            price,
            estimated_hours,
            stock_quantity,
            1 if is_active else 0,
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        conn.close()
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        logger.log_action(
            action_type=ActionTypes.MARKET_ITEM_CREATE,
            user_id=user_id,
            user_name=user['name'],
            details={
                'item_id': item_id,
                'item_name': name,
                'price': price
            }
        )
        
        return jsonify({'message': 'Item created successfully', 'item_id': item_id}), 201
        
    except Exception as e:
        print(f"Error creating market item: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/api/market/items/<item_id>', methods=['PUT'])
@admin_required
def update_market_item(item_id):
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM market_items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        if not item:
            conn.close()
            return jsonify({'error': 'Item not found'}), 404
        
        name = request.form.get('name', item['name'])
        description = request.form.get('description', item['description'] or '')
        price = request.form.get('price')
        estimated_hours = request.form.get('estimated_hours')
        stock_quantity = request.form.get('stock_quantity')
        is_active = request.form.get('is_active', 'true').lower() == 'true'
        
        try:
            price = int(price) if price else item['price']
            estimated_hours = float(estimated_hours) if estimated_hours else item['estimated_hours']
            stock_quantity = int(stock_quantity) if stock_quantity else item['stock_quantity']
        except ValueError:
            conn.close()
            return jsonify({'error': 'Invalid numeric values'}), 400
        
        new_image_url = request.form.get('image_url') 

        if new_image_url:
            image_url = new_image_url

        elif 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                if not allowed_file(file.filename):
                    conn.close()
                    return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400

                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)

                if file_size > 5 * 1024 * 1024:
                    conn.close()
                    return jsonify({'error': 'File size must be less than 5MB'}), 400

                if item['image_url'] and os.path.exists(item['image_url'].lstrip('/')):
                    try:
                        os.remove(item['image_url'].lstrip('/'))
                    except:
                        pass

                filename = f"{db_manager.generate_id()}.{file.filename.rsplit('.', 1)[1].lower()}"
                filepath = os.path.join('static', 'products', filename)

                try:
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    file.save(filepath)
                    image_url = f'/static/products/{filename}'
                except Exception as e:
                    print(f"Error processing image: {e}")
                    conn.close()
                    return jsonify({'error': 'Error processing image'}), 400
        else:
            image_url = item['image_url']

        
        cursor.execute('''
            UPDATE market_items 
            SET name = ?, description = ?, image_url = ?, price = ?, 
                estimated_hours = ?, stock_quantity = ?, is_active = ?, 
                updated_at = ?
            WHERE id = ?
        ''', (
            name,
            description,
            image_url,
            price,
            estimated_hours,
            stock_quantity,
            1 if is_active else 0,
            datetime.now(timezone.utc).isoformat(),
            item_id
        ))
        conn.commit()
        conn.close()
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        logger.log_action(
            action_type=ActionTypes.MARKET_ITEM_UPDATE,
            user_id=user_id,
            user_name=user['name'],
            details={
                'item_id': item_id,
                'item_name': name,
                'price': price
            }
        )
        
        return jsonify({'message': 'Item updated successfully'}), 200
        
    except Exception as e:
        print(f"Error updating market item: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/api/market/items/<item_id>', methods=['DELETE'])
@admin_required
def delete_market_item(item_id):
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM market_items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        if not item:
            conn.close()
            return jsonify({'error': 'Item not found'}), 404
        
        cursor.execute('DELETE FROM market_items WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        logger.log_action(
            action_type=ActionTypes.MARKET_ITEM_DELETE,
            user_id=user_id,
            user_name=user['name'],
            details={
                'item_id': item_id,
                'item_name': item['name']
            }
        )
        
        return jsonify({'message': 'Item deleted successfully'}), 200
        
    except Exception as e:
        print(f"Error deleting market item: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/user/me', methods=['GET'])
@login_required
def get_current_user():
    try:
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user': {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'slack_id': user['slack_id'],
                'tiles_balance': user['tiles_balance']
            }
        }), 200
        
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/market/purchase', methods=['POST'])
@login_required
def purchase_item():
    try:
        data = request.get_json()
        user_id = session.get('user_id')
        
        item_id = data.get('item_id')
        quantity = data.get('quantity', 1)
        contact_info = data.get('contact_info')
        notes = data.get('notes')
        
        if not item_id or not contact_info:
            return jsonify({'error': 'Item ID and contact info are required'}), 400
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM market_items WHERE id = ? AND is_active = 1', (item_id,))
        item = cursor.fetchone()
        if not item:
            conn.close()
            return jsonify({'error': 'Item not found or not available'}), 404
        
        if item['stock_quantity'] != -1 and item['stock_quantity'] < quantity:
            conn.close()
            return jsonify({'error': 'Insufficient stock'}), 400
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404
        
        total_price = item['price'] * quantity
        if user['tiles_balance'] < total_price:
            conn.close()
            return jsonify({'error': 'Insufficient tiles balance'}), 400
    
        order_id = db_manager.generate_id()
        cursor.execute('''
            INSERT INTO orders 
            (id, user_id, item_id, quantity, total_price, status, contact_info, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order_id,
            user_id,
            item_id,
            quantity,
            total_price,
            'pending',
            contact_info,
            notes,
            datetime.now(timezone.utc).isoformat()
        ))
        new_balance = user['tiles_balance'] - total_price
        cursor.execute('UPDATE users SET tiles_balance = ? WHERE id = ?', (new_balance, user_id))
        if item['stock_quantity'] != -1:
            new_stock = item['stock_quantity'] - quantity
            cursor.execute('UPDATE market_items SET stock_quantity = ? WHERE id = ?', (new_stock, item_id))
        
        conn.commit()
        conn.close()
        logger.log_action(
            action_type=ActionTypes.MARKET_PURCHASE,
            user_id=user_id,
            user_name=user['name'],
            details={
                'order_id': order_id,
                'item_id': item_id,
                'item_name': item['name'],
                'quantity': quantity,
                'total_price': total_price,
                'new_balance': new_balance
            }
        )
        
        return jsonify({
            'message': 'Purchase successful',
            'order_id': order_id,
            'new_balance': new_balance
        }), 201
        
    except Exception as e:
        print(f"Error processing purchase: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/market/my-orders', methods=['GET'])
@login_required
def get_my_orders():
    try:
        user_id = session.get('user_id')
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, m.name as item_name, m.image_url as item_image
            FROM orders o
            LEFT JOIN market_items m ON o.item_id = m.id
            WHERE o.user_id = ?
            ORDER BY o.created_at DESC
        ''', (user_id,))
        orders = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({'orders': orders}), 200
        
    except Exception as e:
        print(f"Error fetching user orders: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/api/market/orders', methods=['GET'])
@admin_required
def get_all_orders():
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT o.*, m.name as item_name, u.name as user_name, u.slack_id as user_slack_id
            FROM orders o
            LEFT JOIN market_items m ON o.item_id = m.id
            LEFT JOIN users u ON o.user_id = u.id
            ORDER BY o.created_at DESC
        ''', ())
        orders = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({'orders': orders}), 200
        
    except Exception as e:
        print(f"Error fetching orders: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/api/market/orders/<order_id>', methods=['PUT'])
@admin_required
def update_order_status(order_id):
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if not new_status or new_status not in ['pending', 'processing', 'fulfilled', 'cancelled']:
            return jsonify({'error': 'Invalid status'}), 400
        
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()
        if not order:
            conn.close()
            return jsonify({'error': 'Order not found'}), 404
        
        old_status = order['status']
        if old_status == 'cancelled':
            conn.close()
            return jsonify({'error': 'Cannot change status of a cancelled order'}), 400
        if new_status == 'cancelled' and old_status != 'cancelled':
            cursor.execute('SELECT * FROM users WHERE id = ?', (order['user_id'],))
            user = cursor.fetchone()
            
            if user:
                new_balance = user['tiles_balance'] + order['total_price']
                cursor.execute('''
                    UPDATE users 
                    SET tiles_balance = ?, updated_at = ? 
                    WHERE id = ?
                ''', (new_balance, datetime.now(timezone.utc).isoformat(), user['id']))
                admin_user_id = session.get('user_id')
                admin_user = get_user_by_id(admin_user_id)
                logger.log_action(
                    action_type=ActionTypes.TILES_BALANCE_CHANGE,
                    user_id=admin_user_id,
                    user_name=admin_user['name'],
                    target_user_id=user['id'],
                    details={
                        'reason': 'order_cancelled_refund',
                        'order_id': order_id,
                        'amount': order['total_price'],
                        'old_balance': user['tiles_balance'],
                        'new_balance': new_balance
                    }
                )
        
        fulfilled_at = datetime.now(timezone.utc).isoformat() if new_status == 'fulfilled' else order['fulfilled_at']
        cursor.execute('''
            UPDATE orders 
            SET status = ?, fulfilled_at = ?, updated_at = ?
            WHERE id = ?
        ''', (new_status, fulfilled_at, datetime.now(timezone.utc).isoformat(), order_id))
        
        conn.commit()
        conn.close()
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        if new_status == 'cancelled':
            action_type = ActionTypes.MARKET_ORDER_CANCELLED
        elif new_status == 'fulfilled':
            action_type = ActionTypes.MARKET_ORDER_FULFILLED
        else:
            action_type = ActionTypes.MARKET_ORDER_UPDATE
            
        logger.log_action(
            action_type=action_type,
            user_id=user_id,
            user_name=user['name'],
            target_user_id=order['user_id'],
            details={
                'order_id': order_id,
                'old_status': old_status,
                'new_status': new_status,
                'refunded': new_status == 'cancelled',
                'refund_amount': order['total_price'] if new_status == 'cancelled' else 0
            }
        )
        
        return jsonify({
            'message': 'Order status updated successfully',
            'refunded': new_status == 'cancelled',
            'refund_amount': order['total_price'] if new_status == 'cancelled' else 0
        }), 200
        
    except Exception as e:
        print(f"Error updating order status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/api/market/upload-image', methods=['POST'])
@admin_required
def upload_market_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        if not ('.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, gif, webp'}), 400
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'market')
        os.makedirs(upload_dir, exist_ok=True)
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)
        try:
            img = Image.open(file.stream)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            max_size = (800, 800)
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            if file_extension in ['jpg', 'jpeg']:
                img.save(file_path, 'JPEG', quality=85, optimize=True)
            elif file_extension == 'png':
                img.save(file_path, 'PNG', optimize=True)
            elif file_extension == 'webp':
                img.save(file_path, 'WEBP', quality=85, optimize=True)
            else:
                img.save(file_path, optimize=True)
                
        except ImportError:
            print("PIL not available, saving without optimization")
            file.seek(0)
            file.save(file_path)
        image_url = f"/static/uploads/market/{unique_filename}"
        
        return jsonify({'image_url': image_url}), 200
        
    except Exception as e:
        print(f"Error uploading image: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Internal Server Error'}), 500    

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
        
        # Count active users (users with at least one project)
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
            'user_name': user['name'] if user else 'Unknown',
            'user_slack_id': user.get('slack_id') if user else None
        }), 200
    except Exception as e:
        print(f"Error fetching user projects: {e}")
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
        user_name=user['name'],
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
        user_name=user['name'],
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
        user_name=user['name'],
        target_user_id=project_user_id,
        details={
            'project_id': project_id,
            'project_name': project.get('name'),
            'tiles_awarded': tiles_amount,
            'old_balance': current_balance,
            'new_balance': new_balance,
            'recipient_name': project_user['name'] if project_user else 'Unknown'
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
        user_name=user['name'],
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
        user_name=user['name'],
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

