from flask import Flask, render_template, request, redirect
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)
from flask_socketio import (
    SocketIO,
    emit,
    join_room
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from datetime import datetime

from models import db, User, PrivateMessage, GroupMessage

app = Flask(__name__)

app.config['SECRET_KEY'] = 'secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db.init_app(app)

socketio = SocketIO(app, async_mode='threading')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

online_users = []


# ---------------- LOGIN MANAGER ---------------- #

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------- ROUTES ---------------- #

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

        existing_user = User.query.filter_by(
            username=username
        ).first()

        if existing_user:
            return render_template(
                'register.html',
                error="Username already exists!"
            )

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
                password):

            login_user(user)

            return redirect('/chat')

        return render_template(
            'login.html',
            error="Invalid Username or Password"
        )

    return render_template('login.html')


@app.route('/chat')
@login_required
def chat():

    return render_template(
        'chat.html',
        username=current_user.username
    )


@app.route('/logout')
@login_required
def logout():

    if current_user.username in online_users:
        online_users.remove(current_user.username)

    logout_user()

    return redirect('/login')


# -------- LOAD PRIVATE CHAT HISTORY -------- #

@app.route('/get_messages/<receiver>')
@login_required
def get_messages(receiver):

    if receiver == 'group':
        messages = GroupMessage.query.order_by(
            GroupMessage.timestamp
        ).all()
    else:
        messages = PrivateMessage.query.filter(
            (
                (PrivateMessage.sender == current_user.username) &
                (PrivateMessage.receiver == receiver)
            )
            |
            (
                (PrivateMessage.sender == receiver) &
                (PrivateMessage.receiver == current_user.username)
            )
        ).order_by(
            PrivateMessage.timestamp
        ).all()

    data = []

    for msg in messages:

        data.append({
            'sender': msg.sender,
            'content': msg.content,
            'timestamp': msg.timestamp.strftime("%I:%M %p")
        })

    return data


# ---------------- SOCKET EVENTS ---------------- #

@socketio.on('user_connected')
def user_connected(username):

    join_room('group_chat')
    join_room(f"user_{username}")

    if username not in online_users:
        online_users.append(username)

    emit(
        'update_users',
        online_users,
        broadcast=True
    )


@socketio.on('disconnect')
def disconnected():

    if current_user.is_authenticated:

        if current_user.username in online_users:
            online_users.remove(current_user.username)

        emit(
            'update_users',
            online_users,
            broadcast=True
        )


# -------- JOIN PRIVATE ROOM -------- #

@socketio.on('join_private_room')
def join_private_room(data):

    user1 = data['user1']
    user2 = data['user2']

    room = '_'.join(
        sorted([user1, user2])
    )

    join_room(room)


# -------- TYPING INDICATOR -------- #

@socketio.on('typing')
def typing(data):

    receiver = data['receiver']
    if receiver == 'group':
        room = 'group_chat'
    else:
        room = '_'.join(
            sorted([
                data['username'],
                receiver
            ])
        )

    emit(
        'show_typing',
        data,
        room=room,
        include_self=False
    )


# -------- SEND PRIVATE MESSAGE -------- #

@socketio.on('send_message')
def handle_message(data):

    sender = data['username']
    receiver = data['receiver']
    message_text = data['message']

    if receiver == 'group':
        message = GroupMessage(
            sender=sender,
            content=message_text
        )
        db.session.add(message)
        db.session.commit()

        emit(
            'receive_message',
            {
                'username': sender,
                'message': message_text,
                'timestamp': datetime.now().strftime("%I:%M %p"),
                'receiver': receiver
            },
            room='group_chat'
        )
    else:
        message = PrivateMessage(
            sender=sender,
            receiver=receiver,
            content=message_text
        )
        db.session.add(message)
        db.session.commit()

        emit_data = {
            'username': sender,
            'message': message_text,
            'timestamp': datetime.now().strftime("%I:%M %p"),
            'receiver': receiver
        }
        # Emit to receiver's personal room
        emit('receive_message', emit_data, room=f"user_{receiver}")
        # Emit to sender's personal room
        emit('receive_message', emit_data, room=f"user_{sender}")


# ---------------- MAIN ---------------- #

if __name__ == '__main__':

    with app.app_context():
        db.create_all()

    socketio.run(
        app,
        debug=True,
        allow_unsafe_werkzeug=True
    )