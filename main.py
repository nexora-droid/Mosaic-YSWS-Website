import flask
import hashlib
import random
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, render_template, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "db.sqlite3")

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
db = SQLAlchemy(app)
app.secret_key = os.getenv("SECRET_KEY")

@app.route("/")
def main():
    return render_template('index.html')

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(255))
    role = db.Column(db.String(10), default="User")
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    email = db.Column(db.String(255), nullable=True, unique=True)
    slack_id = db.Column(db.String(255), nullable=True, unique=True)
    verification_code = db.Column(db.Integer)
    is_verified = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()
@app.route("/signin", methods=['GET', 'POST'])
def signin():
    if request.method=='POST': 
        name=request.form['name']
        email = request.form['email']
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.is_verified:
            return render_template("signin.html", message="You're already verified")
        code = random.randint(10000, 99999)
        if existing_user:
            existing_user.verification_code = code
            db.session.commit()

            send_verfication_email(existing_user.email, existing_user.name, code)
            return render_template("signin.html", show_verify=True, message="Code Sent!")
        
        new_user = User(
            name=name,
            email=email,
            role="User",
            verification_code = code,
            is_verified = False
        )
        db.session.add(new_user)
        db.session.commit()

        send_verfication_email(email, name, code)
        session['pending_email'] = email
        return render_template("signin.html", show_verify=True, message="Code Sent!")
    elif 'code' in request.form:
        code = int(request.form('code'))
        pending_email = session.get("pending_email")
        user = User.query.filter_by(email=pending_email).first()
        if user and User.verification_code == code:
            User.is_verified = True;
            db.session.commit()
            return render_template('signin.html', message="Verified Successfully!", show_verify = False)
        else:
            return render_template('signin.html', message="Incorrect Code", show_verify = True)
    return render_template("signin.html")
           
def send_verfication_email(to_email, user_name, code):
    EMAIL = os.getenv("EMAIL_ADDRESS")
    PW= os.getenv("EMAIL_PASSWORD")

    msg = MIMEMultipart()
    msg['From'] = EMAIL
    msg['To'] = to_email
    msg['Subject'] = "Mosaic Verification Code"

    body = f"Hi {user_name}, \n\n Your vericiation code is {code}\nEnter it on the verification form to complete sign up! \n\n Thanks"
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, PW)
        server.sendmail(EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Failed to send email {e}")



if __name__ == "__main__":
    app.run(port=4000, debug=True)