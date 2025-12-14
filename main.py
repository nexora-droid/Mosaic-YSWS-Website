import flask
import hashlib
import random
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, render_template, redirect, session, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import sys
load_dotenv()

app = Flask(__name__)
is_vercel = os.getenv("VERCEL_ENV") == "production"
app.secret_key = os.getenv("SECRET_KEY")
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "db.sqlite3")
is_render=os.getenv("RENDER") == "TRUE"
if (is_render):
    app.config["SQLALCHEMY_DATABASE_URI"]=os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args":{'sslmode': 'require'}
    }
else:
    app.config["SQLALCHEMY_DATABASE_URI"]=f"sqlite:///{DB_PATH}"
db = SQLAlchemy(app)
HACKATIME_API_KEY = os.getenv("HACKATIME_API_KEY")
HACKATIME_BASE_URL = "https://hackatime.hackclub.com/api/v1"
ADMIN_SLACK_IDS = [os.getenv("ADMIN_SLACK_ID", "")]


if not HACKATIME_API_KEY:
    print("WARNING HACKATIME API KEY NOT WORKING!")

def autoconnectHackatime():
    return {
        "Authorization": f"Bearer {HACKATIME_API_KEY}"
    }
def is_admin(user):
    return user and user.slack_id in ADMIN_SLACK_IDS

def get_user_by_id(user_id):
    return User.query.get(user_id)
def get_user_by_slack_id(slack_id):
    return User.query.filter_by(slack_id=slack_id).first()
@app.route("/")
def main():
    return render_template('index.html')

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(255))
    role = db.Column(db.String(10), default="User")
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    slack_id = db.Column(db.String(255), nullable=True, unique=True)
    hackatime_username = db.Column(db.String(255), nullable=True)
    slack_token = db.Column(db.String(255))
    tiles_balance = db.Column(db.Integer, default=0)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    detail = db.Column(db.String(255), nullable = False)
    hackatime_project = db.Column(db.String(255), nullable = False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_seconds = db.Column(db.Integer, default=0)

    # Submission System
    status = db.Column(db.String(50), default="draft")
    approved_hours = db.Column(db.Float, default=0.0)
    screenshot_url = db.Column(db.String(500), nullable=True)
    github_url = db.Column(db.String(500), nullable=True)
    demo_url = db.Column(db.String(500), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    languages = db.Column(db.String(500), nullable=True)
    theme = db.Column(db.String(255), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    assigned_admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


    user = db.relationship('User',foreign_keys=[user_id], backref=db.backref('projects'), lazy=True)
    assigned_admin = db.relationship('User', foreign_keys=[assigned_admin_id], backref=db.backref('assigned_projects'), lazy=True)

class ProjectComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref=db.backref('comments', lazy=True))
    admin = db.relationship('User', foreign_keys=[admin_id])

class Theme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default = datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
with app.app_context():
    db.create_all()



@app.route('/signin', methods=['GET', 'POST'])
def signin():
    client_id = os.getenv('CLIENT_ID')
    redirect_uri = os.getenv('SLACK_REDIRECT_URI')
    redirect_url= f"https://slack.com/oauth/v2/authorize?client_id={client_id}&scope=users:read&user_scope=identity.basic&redirect_uri={redirect_uri}"
    slack_auth_url = redirect_url
    return render_template('signin.html', slack_auth_url=slack_auth_url)
@app.route('/slack/callback', methods=['GET', 'POST'])
def callback():
    code = request.args.get('code')
    if not code:
        return "No Code Recieved from Slack", 400
    payload = {
        "client_id": os.getenv('CLIENT_ID'),
        "client_secret": os.getenv('CLIENT_SECRET'),
        "code": code,
        "redirect_uri": os.getenv('SLACK_REDIRECT_URI')
    }
    response = requests.post("https://slack.com/api/oauth.v2.access", data=payload)
    data = response.json()
    if not data.get('ok'):
        return f"Slack OAuth Failed with error code {data.get('error')}", 400
    
    slack_user_id = data["authed_user"]["id"]
    slack_access_token = data["authed_user"]["access_token"]
    slack_email = data.get("authed", {}).get("email")

    user = User.query.filter_by(slack_id=slack_user_id).first()
    if not user:
        user = User(slack_id=slack_user_id)
        if slack_user_id in ADMIN_SLACK_IDS:
            user.role = "Admin"
        db.session.add(user)
        db.session.commit()
    
    user.slack_token = slack_access_token
    db.session.commit()
    session['user_id'] = user.id

    if is_admin(user):
        return redirect('/admin/dashboard')
    return redirect('/dashboard')
@app.route('/dashboard')
def dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect("/signin")
    user = User.query.get(user_id)
    auto_connected = user.slack_id is not None
    projects = []
    if auto_connected:
        try:
            url = f"{HACKATIME_BASE_URL}/users/{user.slack_id}/stats?features=projects"
            headers = autoconnectHackatime()
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                raw_projects = data.get("data", {}).get('projects', [])
                if isinstance(raw_projects, list):
                    projects = []
                    for proj in raw_projects:
                        projects.append({
                            'name': proj.get('name'),
                            'total_seconds': proj.get('total_seconds', 0),
                            'detail': proj.get('description', '')
                        })
                else:
                    projects=[]
                    print(f"Status Code {response.status_code} Fetching Hackatime Projects")
                    print(f"Response: {response.text}")
        
        except Exception as e:
            print(f"Error Fetching Hackatime Projects {e}")
        
    saved_projects = Project.query.filter_by(user_id=user.id).all()
    stats = get_user_stats(user)
    return render_template(
        "dashboard.html",
        user=user,
        auto_connected = auto_connected,
        projects=projects,
        saved_projects = saved_projects,
        stats = stats,
        is_admin = is_admin(user)
    )
def get_user_stats(user):
    stats = {
        'total_hours': 0,
        'completed_projects': 0,
        'in_review_projects': 0
    }
    if not user.slack_id:
        return stats
    try: 
        headers = autoconnectHackatime()
        url = f"{HACKATIME_BASE_URL}/users/{user.slack_id}/stats"
        response = requests.get(url, headers=headers, timeout=5)

        if response.status_code == 200:
            data = response.json()
            stats['total_hours'] = round(data.get('data', {}).get('total_seconds', 0)/3600, 2)
        stats['completed_projects'] = Project.query.filter_by(user_id=user.id, status='approved').count()
        stats['in_review_projects'] = Project.query.filter_by(user_id=user.id, status='in_review').count()
        
    except Exception as e:
        print(f"Error Fetching user stats: {e}")

    return stats
@app.route("/api/add-project", methods=['POST'])
def add_project_api():
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error' : 'Unauthorized'}), 401
    user = User.query.get(user_id)
    if not user:
        return flask.jsonify({'error': 'User not found'}), 404
    data = request.get_json()
    name = data.get('name')
    detail = data.get('detail')
    hackatime_project = data.get('hack_project')

    if not name:
        return flask.jsonify({'error': 'Missing project name'}), 400
    
    new_project = Project(
        user_id = user.id,
        name=name,
        detail = detail,
        hackatime_project = hackatime_project,
        status = "draft"
    )
    db.session.add(new_project)
    db.session.commit()

    return flask.jsonify({
        'id': new_project.id,
        'name': new_project.name,
        'detail': new_project.detail,
        'hackatime_project': new_project.hackatime_project,
        'status': new_project.status
    }), 201
    
@app.route("/api/submit-project/<int:project_id>", methods=['POST'])
def submit_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    project = Project.query.get(project_id)
    if not project or project.user_id != user_id:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    data = request.get_json()

    project_screenshot_url = data.get('screenshot_url')
    project_github_url = data.get('github_url')
    project_demo_url = data.get('demo_url')
    project_summary = data.get('summary')
    project_languages = data.get('languages')
    project.status = "in_review"
    project.submitted_at = datetime.utcnow()
    
    if ADMIN_SLACK_IDS:
        main_admin = User.query.filter_by(slack_id=ADMIN_SLACK_IDS[0]).first()
        if main_admin:
            project.assigned_admin_id = main_admin.id
    db.session.commit()
    return flask.jsonify({'message': 'Project submitted for review'}), 200

@app.route("/api/project-details/<int:project_id>", methods=['GET'])
def get_project_details(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error' : 'Unauthorized'}), 401
    user = User.query.get(user_id)
    project = Project.query.get(project_id)
    if not project:
        return flask.jsonify({'error': 'Project not found'}), 404
    if not(is_admin(user)) and project.user_id != user.id:
        return flask.jsonify({'error': 'Forbidden'}), 403
    
    raw_hours = 0
    if project.hackatime_project:
        project_user = User.query.get(project.user_id)
        if project_user.slack_id:
            try:
                url = f"{HACKATIME_BASE_URL}/users/{project_user.slack_id}/stats?features=projects"
                headers = autoconnectHackatime()
                response = requests.get(url, headers=headers, timeout=5)

                if response.status_code == 200:
                    data = response.json()
                    raw_projects = data.get("data", {}).get('projects', [])
                    for proj in raw_projects:
                        if proj.get('name') == project.hackatime_project:
                            raw_hours = round(proj.get('total_seconds', 0) / 3600, 2)
                            break
                else:
                    print(f"Status Code {response.status_code} Fetching Hackatime Projects")
                    print(f"Response: {response.text}")
            
            except Exception as e:
                print(f"Error Fetching Hackatime Projects {e}")
    comments = [{
        'admin_name': comment.admin.name,
        'comment': comment.comment,
        'created_at': comment.created_at.strftime("%Y-%m-%d %H:%M:%S")
    } for comment in project.comments]
    return flask.jsonify({
        'id': project.id,
        'name': project.name,
        'detail': project.detail,
        'hackatime_project': project.hackatime_project,
        'status': project.status,
        'raw_hours': raw_hours,
        'approved_hours': project.approved_hours,
        'screenshot_url': project.screenshot_url,
        'github_url': project.github_url,
        'demo_url': project.demo_url,
        'summary': project.summary,
        'languages': project.languages,
        'theme': project.theme,
        'submitted_at': project.submitted_at,
        'reviewed_at': project.reviewed_at,
        'comments': [
            {
                'admin_name': comment.admin.name,
                'comment': comment.comment,
                'created_at': comment.created_at
            } for comment in project.comments
        ]
    }), 200

# ADMIN ROUTES
@app.route('/admin/dashboard')
def admin_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        return redirect("/signin")
    user = User.query.get(user_id)
    if not is_admin(user):
        return redirect("/dashboard")
    assigned_projects = Project.query.filter_by(assigned_admin_id=user.id, status='in_review').all()
    all_pending = Project.query.filter_by(status='in_review').all()

    return render_template(
        'admin_dashboard.html',
        user=user,
        assigned_projects=assigned_projects,
        all_pending=all_pending
    )

@app.route('/admin/api/review-project/<int:project_id>', methods=['POST'])
def admin_review_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error' : 'Unauthorized'}), 401
    
    user = User.query.get(user_id)
    if not is_admin(user):
        return flask.jsonify({'error' : 'Forbidden'}), 403
    
    project = Project.query.get(project_id)
    if not project:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    data = request.get_json()

    project.status = data.get('status', project.status)
    project.approved_hours = float(data.get('approved_hours', project.approved_hours))
    project.reviewed_at = datetime.utcnow()
    project.theme = data.get('theme', project.theme)

    db.session.commit()
    return flask.jsonify({'message': 'Project review updated'}), 200

@app.route('/admin/api/comment-project/<int:project_id>', methods=['POST'])
def admin_comment_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorised'}), 401
    
    user = User.query.get(user_id)
    if not is_admin(user):
        return flask.jsonify({'error' : 'Forbidden'}), 403
    
    project = Project.query.get(project_id)
    if not project:
        return flask.jsonify({'error': 'Project not found'}), 404
    
    data = request.get_json()
    comment_text = data.get('comment')
    if not comment_text:
        return flask.jsonify({'error': 'Comment cannot be empty'}), 400
    
    comment = ProjectComment(
        project_id=project.id,
        admin_id=user.id,
        comment=comment_text
    )
    db.session.add(comment)
    db.session.commit()
    return flask.jsonify({'message': 'Comment added'}), 201

@app.route('/admin/api/assign-project/<int:project_id>', methods=['POST'])
def admin_assign_project(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorised'}), 401
    user = User.query.get(user_id)
    if not is_admin(user):
        return flask.jsonify({'error' : 'Forbidden'}), 403
    
    project = Project.query.get(project_id)
    if not project:
        return flask.jsonify({'error': 'Project not found'}), 404
    project.assigned_admin_id = user.id
    db.session.commit()
    return flask.jsonify({'message': 'Project assigned successfully'}), 200




@app.route('/api/project-hours', methods=['GET'])
def get_project_hours():
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'Error': 'Unauthorised'}), 401
    user = User.query.get(user_id)
    if not user or not user.slack_id:
        return flask.jsonify({'Error ': 'Not logged into Hackatime!'}),404
    project_name =request.args.get('project-name') or request.args.get('project_name')
    if not project_name:
        return flask.jsonify({'Error': 'No Project Name'}), 400
    
    try: 
        url = f'{HACKATIME_BASE_URL}/users/{user.slack_id}/stats?features=projects'
        headers = autoconnectHackatime()
        response = requests.get(url=url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            raw_projects = data.get("data", {}).get('projects', [])
            for proj in raw_projects:
                if proj.get('name')==project_name:
                    hours = proj.get('total_seconds', 0)/3600
                    return flask.jsonify({'hours' : round(hours, 2)}), 200
            return flask.jsonify({'hours': 0, 'message': 'Project not Found'}), 200
        else:
            return flask.jsonify({'Error' : 'Failed to fetch from hackatime'}), 500
        
    except Exception as e:
        print(f"Error fetching hours {e}")
        return flask.jsonify({'Error': 'Internal Server Error'})
@app.route('/leaderboard')
def leaderboard():
    user_id = session.get('user_id')
    user = None
    if user_id:
        user = User.query.get(user_id)

    users_data = []
    all_users = User.query.all()

    for u in all_users:
        approved_projects = Project.query.filter_by(user_id=u.id, status='approved').all()
        total_hours = sum(p.approved_hours for p in approved_projects)
        if total_hours > 0:
            users_data.append({
                'name': u.name or f'User #{u.id}',
                'total_hours': round(total_hours, 2),
                'projects_count': len(approved_projects),
                'tiles': u.tiles_balance if hasattr(u, 'tiles_balance') else 0
            })
    users_data.sort(key=lambda x: x['total_hours'], reverse=True)

    return render_template('leaderboard.html', leaderboard=users_data, user=user)
@app.route('/shop')
def shop():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/signin')
    user = User.query.get(user_id)
    return render_template('shop.html', user=user)
@app.route('/admin/api/award-tiles/<int:project_id>', methods=['POST'])
def admin_award_tiles(project_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    user = User.query.get(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    project=Project.query.get(project_id)
    if not project:
        return flask.jsonify({'error': 'Project not found'}), 404
    data = request.get_json()
    tiles_amount = int(data.get('tiles', 0))
    if tiles_amount<=0:
        return flask.jsonify({'error': 'Invalid tiles amount'}), 400
    project_user = User.query.get(project.user_id)
    if not hasattr(project_user, 'tiles_balance'):
        project_user.tiles_balance = 0
    project_user.tiles_balance += tiles_amount
    db.session.commit()
    return flask.jsonify({
        'message': 'Tiles awarded successfully',
        'new_balance': project_user.tiles_balance
    }), 200

@app.route('/admin/api/add-theme', methods=['POST'])
def admin_add_theme():
    user_id = session.get('user_id')
    user = None
    if not user_id:
        return flask.jsonify({'error': 'Unauthorized'}), 401
    user = User.query.get(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    data = request.get_json()
    theme_name = data.get('name')
    theme_description = data.get('description', '')
    if not theme_name:
        return flask.jsonify({'error': 'Theme name is requried'}), 400
    new_theme = Theme(
        name=theme_name,
        description=theme_description,
        is_active = True
    )
    db.session.add(new_theme)
    db.session.commit()
    return flask.jsonify({
        'message': 'Theme added successsfully',
        'theme': {
            'id': new_theme.id,
            'name': new_theme.name,
            'description': new_theme.description
        }
    }), 201

@app.route('/api/themes', methods=['GET'])
def get_themes():
    themes = Theme.query.filter_by(is_active=True).all()
    return flask.jsonify({
        'themes': [{
            'id': t.id,
            'name': t.name,
            'description': t.description
        } for t in themes]
    }), 200

@app.route('/admin/api/delete-theme/<int:theme_id>', methods=['DELETE'])
def admin_delete_theme(theme_id):
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error': 'Unauthorised'}), 401
    user = User.query.get(user_id)
    if not is_admin(user):
        return flask.jsonify({'error': 'Forbidden'}), 403
    theme = Theme.query.get(theme_id)
    if not theme:
        return flask.jsonify({'error': 'Theme not found'}), 404
    theme.is_active = False
    db.session.commit()
    return flask.jsonify({'message': 'Theme deleted successfully'}), 200
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)