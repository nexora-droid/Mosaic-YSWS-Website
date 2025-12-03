import flask
import hashlib
import random
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, render_template, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from dotenv import load_dotenv
import requests
load_dotenv()

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "db.sqlite3")
HACKATIME_API_KEY = os.getenv("HACKATIME_API_KEY")
HACKATIME_BASE_URL = "https://hackatime.hackclub.com/api/v1"



app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
db = SQLAlchemy(app)
app.secret_key = os.getenv("SECRET_KEY")

if not HACKATIME_API_KEY:
    print("WARNING HACKATIME API KEY NOT WORKING!")

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

class Project(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    detail = db.Column(db.String(255), nullable = False)
    hackatime_project = db.Column(db.String(255), nullable = False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    total_seconds = db.Column(db.Integer, default=0)

    user = db.relationship('User', backref=db.backref('projects'), lazy=True)
with app.app_context():
    db.create_all()

def autoconnectHackatime():
    return {
        "Authorization": f"Bearer {HACKATIME_API_KEY}"
    }
@app.route('/signin', methods=['GET', 'POST'])
def signin():
    client_id = os.getenv('CLIENT_ID')
    redirect_uri = "https://mosaic.conduit.ws/slack/callback"
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
        "redirect_uri": "https://mosaic.conduit.ws/slack/callback"
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
        db.session.add(user)
        db.session.commit()
    
    user.slack_token = slack_access_token
    db.session.commit()
    session['user_id'] = user.id
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
                print("hackatime projects data:", data)
                raw_projects = data.get("data", {}).get('projects', [])
                print("hackatime projects data:", data)
                if isinstance(raw_projects, list):
                    projects = []
                    for proj in raw_projects:
                        projects.append({
                            'name': proj.get('name'),
                            'total_seconds': proj.get('total_seconds', 0),
                            'detail': proj.get('description', '')
                        })
                    print("hackatime projects data:", data)
                else:
                    projects=[]
                    print(f"Status Code {response.status_code} Fetching Hackatime Projects")
                    print(f"Response: {response.text}")
        
        except Exception as e:
            print(f"Error Fetching Hackatime Projects {e}")
        
    saved_projects = Project.query.filter_by(user_id=user.id).all()
    print("Projects to send to html:", projects)
    return render_template(
        "dashboard.html",
        user=user,
        auto_connected = auto_connected,
        projects=projects,
        saved_projects = saved_projects
    )

@app.route("/api/project-hours", methods=['GET'])  
def get_project_hours():
    user_id = session.get('user_id')
    if not user_id:
        return flask.jsonify({'error' : 'Unauthorized'}), 401
    user = User.query.get(user_id)
    if not user:
        return flask.jsonify({'error': 'User not found'}), 404
    
    projectName = request.args.get('project_name')
    if not projectName:
        return flask.jsonify({'error': 'Missing project name'}), 400
    
    total_Seconds = 0
    if user.slack_id:
        try:
            url = f"{HACKATIME_BASE_URL}/users/{user.slack_id}/stats?features=projects"
            headers = autoconnectHackatime()
            response = requests.get(url, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                raw_projects = data.get("data", {}).get('projects', [])
                if isinstance(raw_projects, list):
                    for proj in raw_projects:
                        if proj.get('name') == projectName:
                            total_Seconds = proj.get('total_seconds', 0)
                            break
            else:
                print(f"Status Code {response.status_code} Fetching Hackatime Projects")
                print(f"Response: {response.text}")
        
        except Exception as e:
            print(f"Error Fetching Hackatime Projects {e}")
        
    hours = total_Seconds / 3600
    return flask.jsonify({"hours": hours}), 200
    
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
        hackatime_project = hackatime_project
    )
    db.session.add(new_project)
    db.session.commit()

    return flask.jsonify({
        'id': new_project.id,
        'name': new_project.name,
        'detail': new_project.detail,
        'hackatime_project': new_project.hackatime_project
    }), 201
    


def lookup_hackatime(email):
    url = f"{HACKATIME_BASE_URL}/users/lookup_email/{email}"
    headers = autoconnectHackatime()
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json().get('username')
        return None
    except requests.exceptions.RequestException as e:
        print(f"Hackatimed lookup failed with connection error: {e}")
        return None

@app.route('/leaderboard', methods=['GET', 'POST'])
def leaderboard():
    return render_template('leaderboard.html')


if __name__ == "__main__":
    app.run(port=3700, debug=True)