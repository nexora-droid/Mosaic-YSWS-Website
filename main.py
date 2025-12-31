import os
from flask import Flask, request, render_template, redirect, session, jsonify
from datetime import datetime, timezone
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from audit_logger import audit_logger, ActionTypes
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# firestore init
cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json"))
firebase_admin.initialize_app(cred)
db = firestore.client()

HACKATIME_API_KEY = os.getenv("HACKATIME_API_KEY")
HACKATIME_BASE_URL = "https://hackatime.hackclub.com/api/v1"

#hackclub
HACKCLUB_CLIENT_ID = os.getenv("HACKCLUB_CLIENT_ID")
HACKCLUB_CLIENT_SECRET = os.getenv("HACKCLUB_CLIENT_SECRET")
HACKCLUB_REDIRECT_URI = os.getenv("HACKCLUB_REDIRECT_URI")
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

def autoconnectHackatime():
    return {"Authorization": f"Bearer {HACKATIME_API_KEY}"}

def is_admin(user):
    return user and user.get('slack_id') in ADMIN_SLACK_IDS

@app.context_processor
def utility_processor():
    return dict(is_admin=is_admin)

def get_user_by_id(user_id):
    doc = db.collection('users').document(user_id).get()
    if doc.exists:
        user_data = doc.to_dict()
        user_data['id'] = doc.id
        return user_data
    return None

def get_user_by_slack_id(slack_id):
    users = db.collection('users').where('slack_id', '==', slack_id).limit(1).stream()
    for user in users:
        user_data = user.to_dict()
        user_data['id'] = user.id
        return user_data
    return None

def get_user_by_identity_id(identity_id):
    users = db.collection('users').where('identity_id', '==', identity_id).limit(1).stream()
    for user in users:
        user_data = user.to_dict()
        user_data['id'] = user.id
        return user_data
    return None

def serialize_timestamp(obj):
    if hasattr(obj, 'seconds'):
        return datetime.fromtimestamp(obj.seconds, tz=timezone.utc).isoformat()
    return obj

@app.route("/")
def main():
    return render_template('index.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    auth_url = (
        f"{HACKCLUB_AUTH_BASE}/oauth/authorize?"
        f"client_id={HACKCLUB_CLIENT_ID}&"
        f"redirect_uri={HACKCLUB_REDIRECT_URI}&"
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
        "redirect_uri": HACKCLUB_REDIRECT_URI,
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
        
        if not user:
            # if new user  create account
            user_data = {
                'identity_id': identity_id,
                'slack_id': slack_id,
                'name': f"{first_name} {last_name}" if first_name and last_name else None,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'verification_status': verification_status,
                'role': 'Admin' if slack_id in ADMIN_SLACK_IDS else 'User',
                'date_created': datetime.now(timezone.utc),
                'hackatime_username': None,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'tiles_balance': 0
            }
            user_ref = db.collection('users').document()
            user_ref.set(user_data)
            user_id = user_ref.id
        else:
            #if already a  user update tokens and info
            user_id = user['id']
            db.collection('users').document(user_id).update({
                'access_token': access_token,
                'refresh_token': refresh_token,
                'slack_id': slack_id,
                'name': f"{first_name} {last_name}" if first_name and last_name else user.get('name'),
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'verification_status': verification_status
            })
            user = get_user_by_id(user_id)
        
        session['user_id'] = user_id
        audit_logger.log_action(
            action_type=ActionTypes.USER_LOGIN,
            user_id=user_id,
            user_name=user.get('name'),
            details={
                'slack_id': slack_id,
                'email': email,
                'is_new_user': not user,
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
def dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect("/signin")
    
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
    saved_projects = []
    projects_ref = db.collection('projects').where('user_id', '==', user_id).stream()
    for proj in projects_ref:
        proj_data = proj.to_dict()
        proj_data['id'] = proj.id
        saved_projects.append(proj_data)
    
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
        
        user_id = user['id']
        completed = db.collection('projects').where('user_id', '==', user_id).where('status', '==', 'approved').stream()
        stats['completed_projects'] = len(list(completed))
        
        in_review = db.collection('projects').where('user_id', '==', user_id).where('status', '==', 'in_review').stream()
        stats['in_review_projects'] = len(list(in_review))
        
    except Exception as e:
        print(f"Error Fetching user stats: {e}")
    
    return stats

@app.route('/api/all-users', methods=['GET'])
def get_all_users():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    try:
        users_list = []
        all_users = db.collection('users').stream()
        
        for u in all_users:
            u_data = u.to_dict()
            u_data['id'] = u.id
            all_projects_query = db.collection('projects').where('user_id', '==', u.id).stream()
            all_projects = [p for p in all_projects_query if p.to_dict().get('status') != 'draft']
            
            projects_count = len(all_projects)
            # Get approved projects count
            approved_count = sum(1 for p in all_projects if p.to_dict().get('status') == 'approved')
            # Calculate total hours from approved projects
            total_hours = sum(p.to_dict().get('approved_hours', 0) for p in all_projects if p.to_dict().get('status') == 'approved')
            
            users_list.append({
                'id': u_data['id'],
                'name': u_data.get('name'),
                'email': u_data.get('email'),
                'tiles_balance': u_data.get('tiles_balance', 0),
                'projects_count': projects_count,
                'approved_count': approved_count,
                'total_hours': total_hours
            })
        
        return jsonify({'users': users_list}), 200
    except Exception as e:
        print(f"Error fetching users: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500


@app.route('/api/admin-stats', methods=['GET'])
def get_admin_stats():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    try:
        all_projects = db.collection('projects').stream()
        
        pending_count = 0
        approved_count = 0
        
        for project in all_projects:
            project_data = project.to_dict()
            status = project_data.get('status')
            
            if status == 'in_review':
                pending_count += 1
            elif status == 'approved':
                approved_count += 1
        
        return jsonify({
            'pending_reviews': pending_count,
            'approved_projects': approved_count
        }), 200
    except Exception as e:
        print(f"Error fetching admin stats: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/user-projects/<user_id>', methods=['GET'])
def get_user_projects(user_id):
    admin_id = session.get('user_id')
    if not admin_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    admin = get_user_by_id(admin_id)
    if not is_admin(admin):
        return jsonify({'error': 'Forbidden'}), 403
    
    try:
        projects = []
        projects_ref = db.collection('projects').where('user_id', '==', user_id).stream()
        
        for proj in projects_ref:
            proj_data = proj.to_dict()
            proj_data['id'] = proj.id
            if 'created_at' in proj_data:
                proj_data['created_at'] = serialize_timestamp(proj_data['created_at'])
            if 'submitted_at' in proj_data:
                proj_data['submitted_at'] = serialize_timestamp(proj_data['submitted_at'])
            if 'reviewed_at' in proj_data:
                proj_data['reviewed_at'] = serialize_timestamp(proj_data['reviewed_at'])
            projects.append(proj_data)
        
        projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return jsonify({'projects': projects}), 200
    except Exception as e:
        print(f"Error fetching user projects: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/admin/audit-logs')
def admin_audit_logs():
    user_id = session.get('user_id')
    if not user_id:
        return redirect("/signin")
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return redirect("/dashboard")

    return render_template('admin_audit_logs.html', user=user)

@app.route('/api/admin/audit-logs', methods=['GET'])
def get_audit_logs():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403

    limit = int(request.args.get('limit', 100))
    action_type = request.args.get('action_type')
    filter_user_id = request.args.get('user_id')
    
    try:
        if filter_user_id:
            logs = audit_logger.get_user_actions(filter_user_id, limit)
        elif action_type:
            logs = audit_logger.search_logs(action_type=action_type)[-limit:]
        else:
            logs = audit_logger.get_recent_actions(limit)
        
        return jsonify({'logs': logs}), 200
    except Exception as e:
        print(f"Error fetching audit logs: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/admin/fraud-detection', methods=['GET'])
def fraud_detection():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    try:
        all_logs = audit_logger.get_recent_actions(1000)
        suspicious_activities = []
        
        user_action_counts = {}
        user_recent_actions = {}
        
        for log in all_logs:
            log_user_id = log.get('user_id')
            action_type = log.get('action_type')
            timestamp = log.get('timestamp')
            
            if not log_user_id:
                continue
            
            if log_user_id not in user_action_counts:
                user_action_counts[log_user_id] = {}
                user_recent_actions[log_user_id] = []
            
            if action_type not in user_action_counts[log_user_id]:
                user_action_counts[log_user_id][action_type] = 0
            
            user_action_counts[log_user_id][action_type] += 1
            user_recent_actions[log_user_id].append({
                'action': action_type,
                'timestamp': timestamp
            })
        
        for uid, actions in user_action_counts.items():
            if actions.get('PROJECT_DELETE', 0) > 5:
                suspicious_activities.append({
                    'user_id': uid,
                    'user_name': get_user_by_id(uid).get('name') if get_user_by_id(uid) else 'Unknown',
                    'type': 'EXCESSIVE_DELETIONS',
                    'count': actions['PROJECT_DELETE'],
                    'severity': 'HIGH',
                    'description': f'User deleted {actions["PROJECT_DELETE"]} projects'
                })
            
            if actions.get('PROJECT_CREATE', 0) > 10:
                suspicious_activities.append({
                    'user_id': uid,
                    'user_name': get_user_by_id(uid).get('name') if get_user_by_id(uid) else 'Unknown',
                    'type': 'EXCESSIVE_CREATIONS',
                    'count': actions['PROJECT_CREATE'],
                    'severity': 'MEDIUM',
                    'description': f'User created {actions["PROJECT_CREATE"]} projects'
                })
            
            recent = user_recent_actions[uid][-20:]
            if len(recent) >= 10:
                timestamps = [datetime.fromisoformat(a['timestamp']) for a in recent[-10:]]
                if len(timestamps) > 1:
                    time_span = (timestamps[-1] - timestamps[0]).total_seconds()
                    if time_span < 60:
                        suspicious_activities.append({
                            'user_id': uid,
                            'user_name': get_user_by_id(uid).get('name') if get_user_by_id(uid) else 'Unknown',
                            'type': 'RAPID_ACTIONS',
                            'severity': 'MEDIUM',
                            'description': f'10 actions in {time_span:.1f} seconds'
                        })
        
        for log in all_logs:
            if log.get('action_type') == 'ADMIN_AWARD_TILES':
                tiles_awarded = log.get('details', {}).get('tiles_awarded', 0)
                if tiles_awarded > 1000:
                    suspicious_activities.append({
                        'user_id': log.get('user_id'),
                        'user_name': log.get('user_name'),
                        'type': 'LARGE_TILE_AWARD',
                        'severity': 'HIGH',
                        'description': f'Awarded {tiles_awarded} tiles to {log.get("details", {}).get("recipient_name")}',
                        'timestamp': log.get('timestamp')
                    })
        
        return jsonify({
            'suspicious_activities': suspicious_activities,
            'total_logs_analyzed': len(all_logs)
        }), 200
        
    except Exception as e:
        print(f"Error in fraud detection: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route('/api/admin/user-activity/<user_id>', methods=['GET'])
def get_user_activity_summary(user_id):
    admin_id = session.get('user_id')
    if not admin_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    admin = get_user_by_id(admin_id)
    if not is_admin(admin):
        return jsonify({'error': 'Forbidden'}), 403
    
    try:
        logs = audit_logger.get_user_actions(user_id, limit=500)
        
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


@app.route('/api/delete-project/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    project_ref = db.collection('projects').document(project_id)
    project_doc = project_ref.get()
    
    if not project_doc.exists:
        return jsonify({'error': 'Project not found'}), 404
    
    project = project_doc.to_dict()
    
    if project.get('user_id') != user_id and not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    if not is_admin(user) and project.get('status') != 'draft':
        return jsonify({'error': 'Only draft projects can be deleted'}), 403
    
    try:
        audit_logger.log_action(
            action_type=ActionTypes.PROJECT_DELETE,
            user_id=user_id,
            user_name=user.get('name'),
            details={
                'project_id': project_id,
                'project_name': project.get('name'),
                'project_status': project.get('status'),
                'was_admin_delete': is_admin(user),
                'approved_hours': project.get('approved_hours', 0)
            }
        )
        
        comments_ref = db.collection('project_comments').where('project_id', '==', project_id).stream()
        for comment in comments_ref:
            comment.reference.delete()
        
        project_ref.delete()
        
        return jsonify({'message': 'Project deleted successfully'}), 200
    except Exception as e:
        print(f"Error deleting project: {e}")
        return jsonify({'error': 'Internal Server Error'}), 500

@app.route("/api/add-project", methods=['POST'])
def add_project_api():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    name = data.get('name')
    detail = data.get('detail')
    hackatime_project = data.get('hack_project')
    
    if not name:
        return jsonify({'error': 'Missing project name'}), 400
    
    project_data = {
        'user_id': user_id,
        'name': name,
        'detail': detail,
        'hackatime_project': hackatime_project,
        'status': 'draft',
        'created_at': datetime.now(timezone.utc),
        'total_seconds': 0,
        'approved_hours': 0.0,
        'screenshot_url': None,
        'github_url': None,
        'demo_url': None,
        'summary': None,
        'languages': None,
        'theme': None,
        'submitted_at': None,
        'reviewed_at': None,
        'assigned_admin_id': None
    }
    
    project_ref = db.collection('projects').document()
    project_ref.set(project_data)
    
    audit_logger.log_action(
        action_type=ActionTypes.PROJECT_CREATE,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'project_id': project_ref.id,
            'project_name': name,
            'hackatime_project': hackatime_project,
            'detail': detail
        }
    )
    
    return jsonify({
        'id': project_ref.id,
        'name': name,
        'detail': detail,
        'hackatime_project': hackatime_project,
        'status': 'draft'
    }), 201

@app.route("/api/submit-project/<project_id>", methods=['POST'])
def submit_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    project_ref = db.collection('projects').document(project_id)
    project = project_ref.get()
    
    if not project.exists or project.to_dict().get('user_id') != user_id:
        return jsonify({'error': 'Project not found'}), 404
    
    data = request.get_json()
    
    update_data = {
        'screenshot_url': data.get('screenshot_url'),
        'github_url': data.get('github_url'),
        'demo_url': data.get('demo_url'),
        'summary': data.get('summary'),
        'languages': data.get('languages'),
        'status': 'in_review',
        'submitted_at': datetime.now(timezone.utc)
    }
    
    if ADMIN_SLACK_IDS:
        main_admin = get_user_by_slack_id(ADMIN_SLACK_IDS[0])
        if main_admin:
            update_data['assigned_admin_id'] = main_admin['id']
    
    project_ref.update(update_data)
    
    audit_logger.log_action(
        action_type=ActionTypes.PROJECT_SUBMIT,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'project_id': project_id,
            'project_name': project.to_dict().get('name'),
            'github_url': data.get('github_url'),
            'demo_url': data.get('demo_url'),
            'languages': data.get('languages')
        }
    )
    
    return jsonify({'message': 'Project submitted for review'}), 200

@app.route("/api/project-details/<project_id>", methods=['GET'])
def get_project_details(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    project_ref = db.collection('projects').document(project_id)
    project_doc = project_ref.get()
    
    if not project_doc.exists:
        return jsonify({'error': 'Project not found'}), 404
    
    project = project_doc.to_dict()
    project['id'] = project_doc.id
    
    if not is_admin(user) and project.get('user_id') != user_id:
        return jsonify({'error': 'Forbidden'}), 403
    
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
    
    comments_ref = db.collection('project_comments').where('project_id', '==', project_id).stream()
    comments = []
    for comment_doc in comments_ref:
        comment = comment_doc.to_dict()
        admin = get_user_by_id(comment['admin_id'])
        comments.append({
            'admin_name': admin.get('name') if admin else 'Admin',
            'comment': comment['comment'],
            'created_at': serialize_timestamp(comment.get('created_at', datetime.utcnow()))
        })
    
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
        'submitted_at': serialize_timestamp(project.get('submitted_at')) if project.get('submitted_at') else None,
        'reviewed_at': serialize_timestamp(project.get('reviewed_at')) if project.get('reviewed_at') else None,
        'comments': comments,
        'user_name': project_owner_name
    }), 200

@app.route('/admin/dashboard')
def admin_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect("/signin")
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return redirect("/dashboard")

    return render_template('admin_dashboard.html', user=user)

@app.route('/admin/api/review-project/<project_id>', methods=['POST'])
def admin_review_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    project_doc = project_ref.get()
    
    if not project_doc.exists:
        return jsonify({'error': 'Project not found'}), 404
    
    project_data = project_doc.to_dict()
    data = request.get_json()
    
    old_status = project_data.get('status')
    new_status = data.get('status')
    old_hours = project_data.get('approved_hours', 0)
    new_hours = float(data.get('approved_hours', 0))
    
    update_data = {
        'status': new_status,
        'approved_hours': new_hours,
        'reviewed_at': datetime.now(timezone.utc),
        'theme': data.get('theme')
    }
    
    project_ref.update(update_data)
    
    action_type = ActionTypes.ADMIN_REVIEW_PROJECT
    if new_status == 'approved':
        action_type = ActionTypes.ADMIN_APPROVE_PROJECT
    elif new_status == 'rejected':
        action_type = ActionTypes.ADMIN_REJECT_PROJECT
    
    audit_logger.log_action(
        action_type=action_type,
        user_id=user_id,
        user_name=user.get('name'),
        target_user_id=project_data.get('user_id'),
        details={
            'project_id': project_id,
            'project_name': project_data.get('name'),
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
def admin_comment_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorised'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    project_doc = project_ref.get()
    
    if not project_doc.exists:
        return jsonify({'error': 'Project not found'}), 404
    
    project_data = project_doc.to_dict()
    data = request.get_json()
    comment_text = data.get('comment')
    if not comment_text:
        return jsonify({'error': 'Comment cannot be empty'}), 400
    
    comment_data = {
        'project_id': project_id,
        'admin_id': user_id,
        'comment': comment_text,
        'created_at': datetime.now(timezone.utc)
    }
    
    db.collection('project_comments').add(comment_data)
    
    audit_logger.log_action(
        action_type=ActionTypes.ADMIN_COMMENT_PROJECT,
        user_id=user_id,
        user_name=user.get('name'),
        target_user_id=project_data.get('user_id'),
        details={
            'project_id': project_id,
            'project_name': project_data.get('name'),
            'comment_length': len(comment_text),
            'comment_preview': comment_text[:100]
        }
    )
    
    return jsonify({'message': 'Comment added'}), 201

@app.route('/admin/api/assign-project/<project_id>', methods=['POST'])
def admin_assign_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorised'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    if not project_ref.get().exists:
        return jsonify({'error': 'Project not found'}), 404
    
    project_ref.update({'assigned_admin_id': user_id})
    return jsonify({'message': 'Project assigned successfully'}), 200


@app.route('/api/project-hours', methods=['GET'])
def get_project_hours():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorised'}), 401
    
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
            print(f"Hackatime API returned {response.status_code}")
            return jsonify({'hours': 0, 'message': 'Could not fetch from Hackatime'}), 200
    except requests.exceptions.Timeout:
        print(f"Timeout fetching hours for {project_name}")
        return jsonify({'hours': 0, 'message': 'Hackatime timeout'}), 200
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
    all_users = db.collection('users').stream()
    
    for u in all_users:
        u_data = u.to_dict()
        u_data['id'] = u.id
        
        all_projects_query = db.collection('projects').where('user_id', '==', u.id).stream()
        approved_projects = [p for p in all_projects_query if p.to_dict().get('status') == 'approved']
        
        total_hours = sum(p.to_dict().get('approved_hours', 0) for p in approved_projects)
        projects_count = len(approved_projects)
        
        if total_hours > 0:
            users_data.append({
                'name': u_data.get('name') or f'User #{u.id}',
                'total_hours': round(total_hours, 2),
                'projects_count': projects_count,
                'tiles': u_data.get('tiles_balance', 0)
            })
    
    users_data.sort(key=lambda x: x['total_hours'], reverse=True)
    
    return render_template('leaderboard.html', leaderboard=users_data, user=user)

@app.route('/market')
def shop():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/signin')
    
    user = get_user_by_id(user_id)
    return render_template('soon.html', user=user)

@app.route('/admin/api/award-tiles/<project_id>', methods=['POST'])
def admin_award_tiles(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    project_doc = project_ref.get()
    
    if not project_doc.exists:
        return jsonify({'error': 'Project not found'}), 404
    
    project = project_doc.to_dict()
    data = request.get_json()
    tiles_amount = int(data.get('tiles', 0))
    
    if tiles_amount <= 0:
        return jsonify({'error': 'Invalid tiles amount'}), 400
    
    project_user_id = project['user_id']
    project_user_ref = db.collection('users').document(project_user_id)
    project_user = project_user_ref.get().to_dict()
    
    current_balance = project_user.get('tiles_balance', 0)
    new_balance = current_balance + tiles_amount
    
    project_user_ref.update({'tiles_balance': new_balance})
    
    audit_logger.log_action(
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
            'recipient_name': project_user.get('name')
        }
    )
    
    return jsonify({
        'message': 'Tiles awarded successfully',
        'new_balance': new_balance
    }), 200

@app.route('/admin/api/add-theme', methods=['POST'])
def admin_add_theme():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    theme_name = data.get('name')
    theme_description = data.get('description', '')
    
    if not theme_name:
        return jsonify({'error': 'Theme name is required'}), 400
    
    theme_data = {
        'name': theme_name,
        'description': theme_description,
        'is_active': True,
        'created_at': datetime.utcnow()
    }
    
    theme_ref = db.collection('themes').document()
    theme_ref.set(theme_data)
    
    audit_logger.log_action(
        action_type=ActionTypes.ADMIN_CREATE_THEME,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'theme_id': theme_ref.id,
            'theme_name': theme_name,
            'theme_description': theme_description
        }
    )
    
    return jsonify({
        'message': 'Theme added successfully',
        'theme': {
            'id': theme_ref.id,
            'name': theme_name,
            'description': theme_description
        }
    }), 201

@app.route('/api/themes', methods=['GET'])
def get_themes():
    themes_ref = db.collection('themes').where('is_active', '==', True).stream()
    themes = []
    
    for theme_doc in themes_ref:
        theme = theme_doc.to_dict()
        theme['id'] = theme_doc.id
        themes.append({
            'id': theme['id'],
            'name': theme['name'],
            'description': theme.get('description')
        })
    
    return jsonify({'themes': themes}), 200

@app.route('/admin/api/delete-theme/<theme_id>', methods=['DELETE'])
def admin_delete_theme(theme_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Unauthorised'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return jsonify({'error': 'Forbidden'}), 403
    
    theme_ref = db.collection('themes').document(theme_id)
    theme_doc = theme_ref.get()
    
    if not theme_doc.exists:
        return jsonify({'error': 'Theme not found'}), 404
    
    theme_data = theme_doc.to_dict()
    theme_ref.update({'is_active': False})
    
    audit_logger.log_action(
        action_type=ActionTypes.ADMIN_DELETE_THEME,
        user_id=user_id,
        user_name=user.get('name'),
        details={
            'theme_id': theme_id,
            'theme_name': theme_data.get('name')
        }
    )
    
    return jsonify({'message': 'Theme deleted successfully'}), 200


@app.route('/api/health')
def health():
    return "OK", 200
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4000))
    app.run(
        host="0.0.0.0",
        port=port,
        #ssl_context="adhoc",
        debug=True
    )