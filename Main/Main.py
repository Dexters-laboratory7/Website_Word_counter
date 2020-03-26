from flask import Flask
from flask import render_template
from flask import request
from flask import session
from flask import redirect
from flask import g
from rq import Queue
import redis
from task.tasks import count_words
from flask import url_for
from flask_login import LoginManager,UserMixin,login_user,login_required,logout_user,current_user
from flask_sqlalchemy import SQLAlchemy
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import StringField,PasswordField,BooleanField
from wtforms.validators import InputRequired,Email,Length
from wtforms import ValidationError
from werkzeug.security import generate_password_hash,check_password_hash
import os
import requests
from time import strftime

#-------------->Os-database-environment<--------#

basedir = os.path.abspath(os.path.dirname(__file__))

class Config(object):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir,'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

#-------->flask-intilization<-------------------#
app = Flask(__name__,template_folder='templates')
Bootstrap(app)
#app.config.from_object(Config)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/jesus/proj/edyst-challenge/Main/database.db'
db = SQLAlchemy(app)
# Flask_login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Reddis connection 

rdis = redis.Redis()

#Queue initilization
queue = Queue(connection=rdis)

# User calss
# To create Database table in database if it is not existent you should first import
# Do ---> from Main import db
# Do ---> db.create_all()
class Users(UserMixin,db.Model):
    id = db.Column(db.Integer,primary_key=True)
    username = db.Column(db.String(50),unique=True)
    email = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(80))
# Task class
class Results(db.Model):
    id = db.Column(db.Integer,primary_key=True)
    time = db.Column(db.String)
    username = db.Column(db.String(50))
    url= db.Column(db.String(100))
    jobId = db.Column(db.String(1000),unique=True)
    Createdat = db.Column(db.String(100))
    Enqueuedat = db.Column(db.String(100))
    Finishedat = db.Column(db.String(100))
    wordcount = db.Column(db.Integer)

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

#Login form creation in FlaskForm
class LoginForm(FlaskForm):
    username = StringField('username',validators=[InputRequired(),Length(min=4,max=15)])
    password = PasswordField('password',validators=[InputRequired(),Length(min=8,max=80)])
    remember = BooleanField('remember me')
#Registration form Creation in FlaskForm
class RegisterForm(FlaskForm):
    email = StringField('email',validators=[InputRequired(),Email(message='Invalid email'),Length(max=50)])
    username = StringField('username',validators=[InputRequired(),Length(min=4,max=15)])
    password = PasswordField('password',validators=[InputRequired(),Length(min=8,max=80)])

#Url taking Form
class UrlForm(FlaskForm):
    username = StringField('username',validators=[InputRequired(),Length(min=10,max=800)])

#--------->Taking-unique-Key<-------------------#
app.secret_key = os.urandom(24)

#Index
@app.route('/')
def index():
    return render_template('index.html')

#Login
@app.route('/login',methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate():
        user = Users.query.filter_by(username=form.username.data).first()
        if user:
            if check_password_hash(user.password,form.password.data):
                login_user(user,remember=form.remember.data)
                return redirect(url_for('dashboard'))
        return "<h1>Invalid Credientials</h1>"
        # return form.username.data+" "+form.password.data

    return render_template('login.html',form=form)

#Signup
@app.route('/signup',methods=['GET','POST'])
def signup():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data,method='sha256')
        new_user = Users(username = form.username.data,email=form.email.data,password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return '<h1>New user Created</h1>'
       # return form.username.data+" "+form.password.data+" "+form.email.data
    return render_template('signup.html',form=form)

#dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html',name=current_user.username)
#Adding a task for url Fetching and word counting
@app.route('/add-task',methods=['POST','GET'])
@login_required
def add_task():
    form = UrlForm()
    jobs = queue.jobs
    Message = None
    if form.validate_on_submit():
        wordLength = count_words(form.username.data)
        task = queue.enqueue(count_words,form.username.data)
        jobs = queue.jobs
        queue_length = len(queue)
        new_result = Results(time=strftime('%a, %d %b %Y %H:%M:%S'),username=current_user.username,url=form.username.data,jobId=task.id,Createdat=task.created_at.strftime('%a, %d %b %Y %H:%M:%S'),Enqueuedat=task.enqueued_at.strftime("%c"),Finishedat=strftime('%a, %d %b %Y %H:%M:%S'),wordcount=wordLength)
        db.session.add(new_result)
        db.session.commit()
        Message = f"Task is Queued at {task.enqueued_at.strftime('%a, %d %b %Y %H:%M:%S')}.Number of jobs = {queue_length} jobs Queued"
        return render_template('add_task.html',name=current_user.username,message=Message,jobs=jobs,form=form)

    return render_template('add_task.html',name=current_user.username,message=Message,jobs=jobs,form=form)

#Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)