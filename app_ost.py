import os
import psycopg2
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
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
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

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
    cursor.execute("INSERT INTO users (login, password_hash, subscription_active, device_id, created_at) VALUES (%s, %s, %s, %s, %s)",
                   (login, password_hash, False, None, created_at))
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
            "created_at": user[4],
            "is_admin": is_admin
        })
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")
    device_id = data.get("device_id")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, subscription_active, device_id FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[0], password):
        if user[1]:
            if user[2] is None:
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET device_id = %s WHERE login = %s", (device_id, login))
                conn.commit()
                conn.close()
            elif user[2] != device_id:
                return jsonify({"status": "error", "message": "Логін прив’язано до іншого пристрою"})
            return jsonify({"status": "success", "subscription_active": True})
        return jsonify({"status": "error", "message": "Підписка неактивна"})
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/admin/users", methods=["POST"])
def get_users():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")
    if login != "yokoko" or password != "anonanonNbHq1554o":
        return jsonify({"status": "error", "message": "Невірні адмін-дані"}), 401

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT login, password_hash, subscription_active, created_at FROM users")
    users = [{"login": row[0], "password_hash": row[1], "subscription_active": row[2], "created_at": row[4]} for row in cursor.fetchall()]
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)