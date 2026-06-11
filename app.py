from flask import Flask, render_template, request, redirect
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, Message

app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db.init_app(app)

socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)

login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():
    return redirect('/login')


@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']
        password = generate_password_hash(
            request.form['password']
        )

        if User.query.filter_by(
            username=username
        ).first():

            return "Username already exists!"

        user = User(
            username=username,
            password=password
        )

        db.session.add(user)
        db.session.commit()

        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(
            user.password,
            password
        ):

            login_user(user)

            return redirect('/chat')

    return render_template('login.html')


@app.route('/chat')
@login_required
def chat():

    messages = Message.query.all()

    return render_template(
        'chat.html',
        username=current_user.username,
        messages=messages
    )


@app.route('/logout')
def logout():
    logout_user()
    return redirect('/login')


@socketio.on('send_message')
def handle_message(data):

    message = Message(
        username=data['username'],
        content=data['message']
    )

    db.session.add(message)
    db.session.commit()

    emit(
        'receive_message',
        data,
        broadcast=True
    )


if __name__ == '__main__':

    with app.app_context():
        db.create_all()

    socketio.run(
        app,
        debug=True
    )