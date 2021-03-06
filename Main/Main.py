
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
from sqlalchemy import create_engine
import time


#--------------Os-database-environment<--------#

basedir = os.path.abspath(os.path.dirname(__file__))

## Config for database Sqlalchemy and database setup
class Config(object):
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir,'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

#-------->flask-intilization<-------------------#
app = Flask(__name__,template_folder='templates')
Bootstrap(app)
#app.config.from_object(Config)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/database/database.db'
db = SQLAlchemy(app)
# Flask_login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Reddis connection 

rdis = redis.Redis()

#Queue initilization
queue = Queue(connection=rdis)

# Create engine path Decleration
engine = create_engine('sqlite:////tmp/database/database.db')

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
    username = db.Column(db.String(50))
    url= db.Column(db.String(100))
    jobId = db.Column(db.String(1000),unique=True)
    Enqueuedat = db.Column(db.String(100))
    wordcount = db.Column(db.Integer)
    Status = db.Column(db.String(20))
    Time_taken = db.Column(db.String(20))
    Errors = db.Column(db.String(30))
    Error_description = db.Column(db.String(200))

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

#Login form creation in FlaskForm
class LoginForm(FlaskForm):
    username = StringField('username',validators=[InputRequired(),Length(min=4,max=15)])
    password = PasswordField('password',validators=[InputRequired(),Length(min=8,max=200)])
    remember = BooleanField('remember me')
#Registration form Creation in FlaskForm
class RegisterForm(FlaskForm):
    email = StringField('email',validators=[InputRequired(),Email(message='Invalid email'),Length(max=50)])
    username = StringField('username',validators=[InputRequired(),Length(min=4,max=15)])
    password = PasswordField('password',validators=[InputRequired(),Length(min=8,max=200)])

#Url taking Form
class UrlForm(FlaskForm):
    url = StringField('url',validators=[InputRequired(),Length(min=10,max=800)])

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
                form = UrlForm()
                return render_template('index.html',name=current_user.username)
            else:
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
        return render_template('login.html',message="Record Created Login to continue",form=None)
       # return form.username.data+" "+form.password.data+" "+form.email.data
    return render_template('signup.html',form=form)

#dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    
    query = engine.execute('select * from results ')
    all_results = query.fetchall()

    return render_template('add_task.html',name=current_user.username,list_all= all_results)

#Adding a task for url Fetching and word counting
@app.route('/add-task',methods=['POST','GET'])
@login_required
def add_task():
    form = UrlForm()
    jobs = queue.jobs
    Message = None
    if form.validate_on_submit():
        start = time.time()
        https = form.url.data[0:8]
        http = form.url.data[0:7]
        boolean = False
        if http == "http://":
            boolean = True
        elif https == "https://":
            boolean = True
        if not boolean:
            return render_template('add_task.html',name=current_user.username,message="Enter Full url with Http and https",jobs=jobs,form=form)
        try:
            r = requests.get(form.url.data)
        except (requests.exceptions.ConnectionError,requests.ConnectionError,requests.ConnectTimeout) as v:
            return render_template('add_task.html',name=current_user.username,message="Enter a valid Url",jobs=jobs,form=form)
        r = requests.get(form.url.data)
        status = ""
        error = ""
        error_desc = ""
        try:
            r.raise_for_status()
        except (requests.exceptions.BaseHTTPError,requests.exceptions.ConnectionError,requests.exceptions.ConnectTimeout,requests.exceptions.InvalidProxyURL,requests.exceptions.RetryError,requests.exceptions.URLRequired,requests.exceptions.HTTPError) as v:
            error_desc = str(v)
        
        if r.status_code == 200:
            status = "Success"
            error = r.status_code
            error_desc = "None"
        else:
            status = "Error"
            error = str(r.status_code)
              
            
        wordLength = count_words(form.url.data)
        task = queue.enqueue(count_words,form.url.data)
        jobs = queue.jobs
        queue_length = len(queue)
        end = time.time()
        elapsed_time = end - start
        new_result = Results(username=current_user.username,url=form.url.data,jobId=task.id,Enqueuedat=task.enqueued_at.strftime("%c"),Status=status,wordcount=wordLength,Time_taken=elapsed_time,Errors=error,Error_description=error_desc)
        db.session.add(new_result)
        db.session.commit()
        Message = f"Task is Queued at {task.enqueued_at.strftime('%a, %d %b %Y %H:%M:%S')}.Number of jobs = {queue_length} jobs Queued"
        query = engine.execute('select * from results ')
        all_results = query.fetchall()
        return render_template('add_task.html',name=current_user.username,message=Message,jobs=jobs,form=form,list_all= all_results)
    query = engine.execute('select * from results ')
    all_results = query.fetchall()
    return render_template('add_task.html',name=current_user.username,message=Message,jobs=jobs,form=form,list_all= all_results)

#Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)
