import os
import psycopg2
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

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
            subscription_expiry TIMESTAMP
        )
    """)
    conn.commit()
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
    cursor.execute("INSERT INTO users (login, password_hash, subscription_active, device_id, created_at, session_active, subscription_expiry) VALUES (%s, %s, %s, %s, %s, %s, %s)",
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
    cursor.execute("SELECT login, password_hash, subscription_active, created_at, subscription_expiry FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[1], password):
        expiry = user[4]
        active = user[2]
        now = datetime.utcnow()
        if active and expiry and now > expiry:
            cursor.execute("UPDATE users SET subscription_active = FALSE, subscription_expiry = NULL WHERE login = %s", (login,))
            conn.commit()
            active = False

        is_admin = login == "yokoko" and password == "anonanonNbHq1554o"
        conn.close()
        return jsonify({
            "status": "success",
            "login": user[0],
            "subscription_active": active,
            "created_at": user[3],
            "is_admin": is_admin
        })
    conn.close()
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, subscription_active, session_active, subscription_expiry FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password):
        expiry = user[3]
        active = user[1]
        now = datetime.utcnow()
        if active and expiry and now > expiry:
            cursor.execute("UPDATE users SET subscription_active = FALSE, subscription_expiry = NULL WHERE login = %s", (login,))
            conn.commit()
            conn.close()
            return jsonify({"status": "error", "message": "Підписка закінчилася"})

        if active:
            if not user[2]:  # session_active
                cursor.execute("UPDATE users SET session_active = TRUE WHERE login = %s", (login,))
                conn.commit()
                conn.close()
                return jsonify({"status": "success", "subscription_active": True})
            conn.close()
            return jsonify({"status": "error", "message": "Сесія вже активна на іншому пристрої"})
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
    cursor.execute("SELECT login, password_hash, subscription_active, created_at, session_active, subscription_expiry FROM users")
    users = [{"login": row[0], "password_hash": row[1], "subscription_active": row[2], "created_at": row[3], "session_active": row[4], "subscription_expiry": str(row[5]) if row[5] else None} for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "users": users})

@app.route("/api/admin/update_subscription", methods=["POST"])
def update_subscription():
    data = request.get_json()
    admin_login = data.get("login")
    admin_password = data.get("password")
    if admin_login != "yokoko" or admin_password != "anonanonNbHq1554o":
        return jsonify({"status": "error", "message": "Невірні адмін-дані"}), 401

    user_login = data.get("user_login")
    duration = data.get("duration")

    durations = {
        "1 hour": timedelta(hours=1),
        "3 hours": timedelta(hours=3),
        "6 hours": timedelta(hours=6),
        "12 hours": timedelta(hours=12),
        "24 hours": timedelta(hours=24),
        "3 days": timedelta(days=3),
        "15 days": timedelta(days=15),
        "30 days": timedelta(days=30),
        "60 days": timedelta(days=60),
        "90 days": timedelta(days=90),
        "120 days": timedelta(days=120),
        "150 days": timedelta(days=150),
    }

    conn = get_db()
    cursor = conn.cursor()

    if duration == "deactivate":
        cursor.execute("UPDATE users SET subscription_active = %s, subscription_expiry = %s WHERE login = %s", (False, None, user_login))
    elif duration in durations:
        delta = durations[duration]
        expiry = datetime.utcnow() + delta
        cursor.execute("UPDATE users SET subscription_active = %s, subscription_expiry = %s WHERE login = %s", (True, expiry, user_login))
    else:
        conn.close()
        return jsonify({"status": "error", "message": "Невірна тривалість"}), 400

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
