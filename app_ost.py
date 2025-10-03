import os
import psycopg2
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_cors import CORS
import uuid

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Создаем таблицу если не существует
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            login TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            subscription_active BOOLEAN NOT NULL,
            device_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    
    # Проверяем и добавляем колонки по отдельности с новыми транзакциями
    try:
        cursor.execute("SELECT session_token FROM users LIMIT 1")
    except psycopg2.Error:
        conn.rollback()
        cursor.execute("ALTER TABLE users ADD COLUMN session_token TEXT")
        conn.commit()
        print("Added session_token column")
    else:
        conn.rollback()
    
    # Новая транзакция для session_active
    try:
        cursor.execute("SELECT session_active FROM users LIMIT 1")
    except psycopg2.Error:
        conn.rollback()
        cursor.execute("ALTER TABLE users ADD COLUMN session_active BOOLEAN DEFAULT FALSE")
        conn.commit()
        print("Added session_active column")
    else:
        conn.rollback()
    
    conn.close()

init_db()

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT login FROM users WHERE login = %s", (login,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"status": "error", "message": "Логін уже зайнятий"})

    password_hash = generate_password_hash(password)
    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO users (login, password_hash, subscription_active, device_id, created_at, session_active, session_token) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                   (login, password_hash, False, None, created_at, False, None))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT login, password_hash, subscription_active, created_at FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[1], password):
        is_admin = login == "yokoko" and password == "anonanonNbHq1554o"
        return jsonify({
            "status": "success",
            "login": user[0],
            "subscription_active": user[2],
            "created_at": user[3],
            "is_admin": is_admin
        })
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, subscription_active FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password):
        if user[1]:  # subscription_active
            session_token = str(uuid.uuid4())
            cursor.execute("UPDATE users SET session_active = TRUE, session_token = %s WHERE login = %s", (session_token, login))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "subscription_active": True, "session_token": session_token})
        conn.close()
        return jsonify({"status": "error", "message": "Підписка неактивна"})
    conn.close()
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/logout", methods=["POST"])
def logout():
    data = request.get_json()
    login = data.get("login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET session_active = FALSE, session_token = NULL WHERE login = %s", (login,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route("/api/check_session", methods=["POST"])
def check_session():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")
    provided_token = data.get("session_token")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, session_active, session_token FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password) and user[1] and user[2] == provided_token:
        conn.close()
        return jsonify({"status": "success", "session_active": True})
    conn.close()
    return jsonify({"status": "success", "session_active": False})

@app.route("/api/admin/users", methods=["POST"])
def get_users():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")
    if login != "yokoko" or password != "anonanonNbHq1554o":
        return jsonify({"status": "error", "message": "Невірні адмін-дані"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT login, password_hash, subscription_active, created_at, session_active, session_token FROM users")
    users = [{"login": row[0], "password_hash": row[1], "subscription_active": row[2], "created_at": row[3], "session_active": row[4], "session_token": row[5]} for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "users": users})

@app.route("/api/admin/update_subscription", methods=["POST"])
def update_subscription():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")
    if login != "yokoko" or password != "anonanonNbHq1554o":
        return jsonify({"status": "error", "message": "Невірні адмін-дані"}), 401

    user_login = data.get("user_login")
    subscription_active = data.get("subscription_active")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET subscription_active = %s WHERE login = %s", (subscription_active, user_login))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route("/api/force_logout", methods=["POST"])
def force_logout():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password):
        cursor.execute("UPDATE users SET session_active = FALSE, session_token = NULL WHERE login = %s", (login,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Сесія завершена"})
    conn.close()
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
