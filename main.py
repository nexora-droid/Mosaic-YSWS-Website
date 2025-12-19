import flask
import os
from flask import Flask, request, render_template, redirect, session, url_for, flash
from datetime import datetime, timedelta
import requests
import firebase_admin
from firebase_admin import credentials, firestore
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
                'date_created': datetime.utcnow(),
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
            url = f"{HACKATIME_BASE_URL}/users/{user['slack_id']}/stats?features=projects"
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
        stats=stats,
        is_admin=is_admin(user)
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

@app.route("/api/add-project", methods=['POST'])
def add_project_api():
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not user:
        return flask.jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    name = data.get('name')
    detail = data.get('detail')
    hackatime_project = data.get('hack_project')
    
    if not name:
        return flask.jsonify({'error': 'Missing project name'}), 400
    
    project_data = {
        'user_id': user_id,
        'name': name,
        'detail': detail,
        'hackatime_project': hackatime_project,
        'status': 'draft',
        'created_at': datetime.utcnow(),
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
    
    return flask.jsonify({
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
        return flask.jsonify({'error': 'Unauthorized'}), 401
    
    project_ref = db.collection('projects').document(project_id)
    project = project_ref.get()
    
    if not project.exists or project.to_dict().get('user_id') != user_id:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    data = request.get_json()
    
    update_data = {
        'screenshot_url': data.get('screenshot_url'),
        'github_url': data.get('github_url'),
        'demo_url': data.get('demo_url'),
        'summary': data.get('summary'),
        'languages': data.get('languages'),
        'status': 'in_review',
        'submitted_at': datetime.utcnow()
    }
    
    if ADMIN_SLACK_IDS:
        main_admin = get_user_by_slack_id(ADMIN_SLACK_IDS[0])
        if main_admin:
            update_data['assigned_admin_id'] = main_admin['id']
    
    project_ref.update(update_data)
    
    return flask.jsonify({'message': 'Project submitted for review'}), 200

@app.route("/api/project-details/<project_id>", methods=['GET'])
def get_project_details(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    project_ref = db.collection('projects').document(project_id)
    project_doc = project_ref.get()
    
    if not project_doc.exists:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    project = project_doc.to_dict()
    project['id'] = project_doc.id
    
    if not is_admin(user) and project.get('user_id') != user_id:
        return flask.jsonify({'error': 'Forbidden'}), 403
    
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
            'created_at': comment['created_at']
        })
    
    return flask.jsonify({
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
        'comments': comments
    }), 200

@app.route('/admin/dashboard')
def admin_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect("/signin")
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return redirect("/dashboard")

    assigned_projects = []
    assigned_ref = db.collection('projects').where('assigned_admin_id', '==', user_id).where('status', '==', 'in_review').stream()
    for proj in assigned_ref:
        proj_data = proj.to_dict()
        proj_data['id'] = proj.id
        proj_data['user'] = get_user_by_id(proj_data['user_id'])
        assigned_projects.append(proj_data)
    all_pending = []
    pending_ref = db.collection('projects').where('status', '==', 'in_review').stream()
    for proj in pending_ref:
        proj_data = proj.to_dict()
        proj_data['id'] = proj.id
        proj_data['user'] = get_user_by_id(proj_data['user_id'])
        if proj_data.get('assigned_admin_id'):
            proj_data['assigned_admin'] = get_user_by_id(proj_data['assigned_admin_id'])
        all_pending.append(proj_data)
    
    return render_template(
        'admin_dashboard.html',
        user=user,
        assigned_projects=assigned_projects,
        all_pending=all_pending
    )

@app.route('/admin/api/review-project/<project_id>', methods=['POST'])
def admin_review_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    if not project_ref.get().exists:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    data = request.get_json()
    
    update_data = {
        'status': data.get('status'),
        'approved_hours': float(data.get('approved_hours', 0)),
        'reviewed_at': datetime.utcnow(),
        'theme': data.get('theme')
    }
    
    project_ref.update(update_data)
    return flask.jsonify({'message': 'Project review updated'}), 200

@app.route('/admin/api/comment-project/<project_id>', methods=['POST'])
def admin_comment_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorised'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    if not project_ref.get().exists:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    data = request.get_json()
    comment_text = data.get('comment')
    if not comment_text:
        return flask.jsonify({'error': 'Comment cannot be empty'}), 400
    
    comment_data = {
        'project_id': project_id,
        'admin_id': user_id,
        'comment': comment_text,
        'created_at': datetime.utcnow()
    }
    
    db.collection('project_comments').add(comment_data)
    return flask.jsonify({'message': 'Comment added'}), 201

@app.route('/admin/api/assign-project/<project_id>', methods=['POST'])
def admin_assign_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorised'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    if not project_ref.get().exists:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    project_ref.update({'assigned_admin_id': user_id})
    return flask.jsonify({'message': 'Project assigned successfully'}), 200




@app.route('/api/project-hours', methods=['GET'])
def get_project_hours():
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'Error': 'Unauthorised'}), 401
    
    user = get_user_by_id(user_id)
    if not user or not user.get('slack_id'):
        return flask.jsonify({'Error': 'Not logged into Hackatime!'}), 404
    
    project_name = request.args.get('project-name') or request.args.get('project_name')
    if not project_name:
        return flask.jsonify({'Error': 'No Project Name'}), 400
    
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
                    return flask.jsonify({'hours': round(hours, 2)}), 200
            return flask.jsonify({'hours': 0, 'message': 'Project not Found'}), 200
        else:
            return flask.jsonify({'Error': 'Failed to fetch from hackatime'}), 500
    except Exception as e:
        print(f"Error fetching hours {e}")
        return flask.jsonify({'Error': 'Internal Server Error'}), 500

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
        
        # get approved proj
        approved_projects = db.collection('projects').where('user_id', '==', u.id).where('status', '==', 'approved').stream()
        total_hours = sum(p.to_dict().get('approved_hours', 0) for p in approved_projects)
    
        approved_projects = db.collection('projects').where('user_id', '==', u.id).where('status', '==', 'approved').stream()
        projects_count = len(list(approved_projects))
        
        if total_hours > 0:
            users_data.append({
                'name': u_data.get('name') or f'User #{u.id}',
                'total_hours': round(total_hours, 2),
                'projects_count': projects_count,
                'tiles': u_data.get('tiles_balance', 0)
            })
    
    users_data.sort(key=lambda x: x['total_hours'], reverse=True)
    
    return render_template('leaderboard.html', leaderboard=users_data, user=user)

@app.route('/shop')
def shop():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/signin')
    
    user = get_user_by_id(user_id)
    return render_template('shop.html', user=user)

@app.route('/admin/api/award-tiles/<project_id>', methods=['POST'])
def admin_award_tiles(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    
    project_ref = db.collection('projects').document(project_id)
    project_doc = project_ref.get()
    
    if not project_doc.exists:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    project = project_doc.to_dict()
    data = request.get_json()
    tiles_amount = int(data.get('tiles', 0))
    
    if tiles_amount <= 0:
        return flask.jsonify({'error': 'Invalid tiles amount'}), 400
    
    project_user_id = project['user_id']
    project_user_ref = db.collection('users').document(project_user_id)
    project_user = project_user_ref.get().to_dict()
    
    current_balance = project_user.get('tiles_balance', 0)
    new_balance = current_balance + tiles_amount
    
    project_user_ref.update({'tiles_balance': new_balance})
    
    return flask.jsonify({
        'message': 'Tiles awarded successfully',
        'new_balance': new_balance
    }), 200

@app.route('/admin/api/add-theme', methods=['POST'])
def admin_add_theme():
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    
    data = request.get_json()
    theme_name = data.get('name')
    theme_description = data.get('description', '')
    
    if not theme_name:
        return flask.jsonify({'error': 'Theme name is required'}), 400
    
    theme_data = {
        'name': theme_name,
        'description': theme_description,
        'is_active': True,
        'created_at': datetime.utcnow()
    }
    
    theme_ref = db.collection('themes').document()
    theme_ref.set(theme_data)
    
    return flask.jsonify({
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
    
    return flask.jsonify({'themes': themes}), 200

@app.route('/admin/api/delete-theme/<theme_id>', methods=['DELETE'])
def admin_delete_theme(theme_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorised'}), 401
    
    user = get_user_by_id(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    
    theme_ref = db.collection('themes').document(theme_id)
    if not theme_ref.get().exists:
        return flask.jsonify({'error': 'Theme not found'}), 404
    
    theme_ref.update({'is_active': False})
    return flask.jsonify({'message': 'Theme deleted successfully'}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4000))
    app.run(
        host="0.0.0.0",
        port=port,
        ssl_context="adhoc",
        debug=True
    )