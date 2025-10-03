import os
import psycopg2
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_cors import CORS
import threading
import time

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

# Словарь для хранения активных сессий (время последней активности)
active_sessions = {}

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            login TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            subscription_active BOOLEAN NOT NULL,
            device_id TEXT,
            created_at TEXT NOT NULL,
            session_active BOOLEAN DEFAULT FALSE,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Фоновая задача для очистки неактивных сессий
def cleanup_sessions():
    while True:
        try:
            conn = get_db()
            cursor = conn.cursor()
            # Сбрасываем сессии, где последняя активность была более 5 минут назад
            cursor.execute("""
                UPDATE users 
                SET session_active = FALSE 
                WHERE session_active = TRUE 
                AND last_activity < NOW() - INTERVAL '5 minutes'
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error in session cleanup: {e}")
        time.sleep(60)  # Проверяем каждую минуту

# Запускаем фоновую задачу
cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
cleanup_thread.start()

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
    cursor.execute("INSERT INTO users (login, password_hash, subscription_active, device_id, created_at, session_active) VALUES (%s, %s, %s, %s, %s, %s)",
                   (login, password_hash, False, None, created_at, False))
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
    cursor.execute("SELECT password_hash, subscription_active, session_active FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password):
        if user[1]:  # subscription_active
            if not user[2]:  # session_active
                cursor.execute("UPDATE users SET session_active = TRUE, last_activity = CURRENT_TIMESTAMP WHERE login = %s", (login,))
                conn.commit()
                conn.close()
                return jsonify({"status": "success", "subscription_active": True})
            conn.close()
            return jsonify({"status": "error", "message": "Сесія вже активна на іншому пристрої"})
        conn.close()
        return jsonify({"status": "error", "message": "Підписка неактивна"})
    conn.close()
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/check_session", methods=["POST"])
def check_session():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, session_active, last_activity FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password):
        if user[1]:  # session_active
            # Обновляем время последней активности
            cursor.execute("UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE login = %s", (login,))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "session_active": True})
        conn.close()
        return jsonify({"status": "error", "message": "Сесія неактивна"})
    conn.close()
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/logout", methods=["POST"])
def logout():
    data = request.get_json()
    login = data.get("login")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET session_active = FALSE WHERE login = %s", (login,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route("/api/admin/users", methods=["POST"])
def get_users():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")
    if login != "yokoko" or password != "anonanonNbHq1554o":
        return jsonify({"status": "error", "message": "Невірні адмін-дані"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT login, password_hash, subscription_active, created_at, session_active FROM users")
    users = [{"login": row[0], "password_hash": row[1], "subscription_active": row[2], "created_at": row[3], "session_active": row[4]} for row in cursor.fetchall()]
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
        cursor.execute("UPDATE users SET session_active = FALSE WHERE login = %s", (login,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Стара сесія завершена"})
    conn.close()
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
