import os
import psycopg2
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_cors import CORS
import uuid
import pyotp
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # табличку   /* ====================   Copyright © 2025 [DUDKA_ARTEM_ДУДКА_АРТЕМ_3676006734]. All rights reserved.) ==================== */
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            login TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            subscription_active BOOLEAN NOT NULL,
            subscription_expires TIMESTAMP,
            device_id TEXT,
            created_at TEXT NOT NULL,
            session_token TEXT,
            session_active BOOLEAN DEFAULT FALSE
        )
    """)
    conn.commit()
    
    # перевірки колонок транзакції
    try:
        cursor.execute("SELECT subscription_expires FROM users LIMIT 1")
    except psycopg2.Error:
        conn.rollback()
        cursor.execute("ALTER TABLE users ADD COLUMN subscription_expires TIMESTAMP")
        conn.commit()
        print("Added subscription_expires column")
    else:
        conn.rollback()
    
    try:
        cursor.execute("SELECT session_token FROM users LIMIT 1")
    except psycopg2.Error:
        conn.rollback()
        cursor.execute("ALTER TABLE users ADD COLUMN session_token TEXT")
        conn.commit()
        print("Added session_token column")
    else:
        conn.rollback()
    
    try:
        cursor.execute("SELECT session_active FROM users LIMIT 1")
    except psycopg2.Error:
        conn.rollback()
        cursor.execute("ALTER TABLE users ADD COLUMN session_active BOOLEAN DEFAULT FALSE")
        conn.commit()
        print("Added session_active column")
    else:
        conn.rollback()
    
    # колонка таблиці 
    try:
        cursor.execute("SELECT is_admin FROM users LIMIT 1")
    except psycopg2.Error:
        conn.rollback()
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE")
        conn.commit()
        print("Added is_admin column")
    else:
        conn.rollback()
    
    # колонка таболиці 
    try:
        cursor.execute("SELECT totp_secret FROM users LIMIT 1")
    except psycopg2.Error:
        conn.rollback()
        cursor.execute("ALTER TABLE users ADD COLUMN totp_secret TEXT")
        conn.commit()
        print("Added totp_secret column")
    else:
        conn.rollback()
    
    # база рух
    
    
    conn.close()

init_db()

def is_subscription_active(subscription_active, subscription_expires):
    """перепіряємо активна підпска з часом """
    if not subscription_active:
        return False
    if subscription_expires:
        return datetime.utcnow() < subscription_expires
    return True

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
    cursor.execute("INSERT INTO users (login, password_hash, subscription_active, subscription_expires, device_id, created_at, session_active, session_token, is_admin) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                   (login, password_hash, False, None, None, created_at, False, None, False))
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
    cursor.execute("SELECT login, password_hash, subscription_active, subscription_expires, created_at, is_admin, totp_secret FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()
    
    if user and check_password_hash(user[1], password):
        # перевіряємо активність підписки з чаасом /* ====================   Copyright © 2025 [DUDKA_ARTEM_ДУДКА_АРТЕМ_3676006734]. All rights reserved.) ==================== */
        subscription_active = is_subscription_active(user[2], user[3])
        
        # якщо підпска не альо ф5
        if user[2] and not subscription_active:
            cursor.execute("UPDATE users SET subscription_active = FALSE, subscription_expires = NULL WHERE login = %s", (login,))
            conn.commit()
        
        is_admin = user[5]
        totp_secret = user[6]
        
        if is_admin:
            if totp_secret:
                conn.close()
                return jsonify({
                    "status": "2fa_required",
                    "login": user[0],
                    "subscription_active": subscription_active,
                    "subscription_expires": user[3].strftime("%Y-%m-%d %H:%M:%S") if user[3] else None,
                    "created_at": user[4],
                    "is_admin": is_admin
                })
            else:
                conn.close()
                return jsonify({
                    "status": "2fa_setup_required",
                    "login": user[0],
                    "subscription_active": subscription_active,
                    "subscription_expires": user[3].strftime("%Y-%m-%d %H:%M:%S") if user[3] else None,
                    "created_at": user[4],
                    "is_admin": is_admin
                })
        
        conn.close()
        
        return jsonify({
            "status": "success",
            "login": user[0],
            "subscription_active": subscription_active,
            "subscription_expires": user[3].strftime("%Y-%m-%d %H:%M:%S") if user[3] else None,
            "created_at": user[4],
            "is_admin": is_admin
        })
    conn.close()
    return jsonify({"status": "error", "message": "Невірний логін або пароль"})

@app.route("/api/setup_2fa", methods=["POST"])
def setup_2fa():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, is_admin, totp_secret FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password) and user[1]:  # хеш
        if not user[2]:  # крктнй вхід крствча   
            secret = pyotp.random_base32()
            cursor.execute("UPDATE users SET totp_secret = %s WHERE login = %s", (secret, login))
            conn.commit()

            uri = pyotp.TOTP(secret).provisioning_uri(name=login, issuer_name="Passport Reader")
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(uri)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            buffered = BytesIO()
            img.save(buffered)
            base64_qr = base64.b64encode(buffered.getvalue()).decode('utf-8')

            conn.close()
            return jsonify({"status": "success", "qr_image": base64_qr, "secret": secret})
        conn.close()
        return jsonify({"status": "error", "message": "2FA already set up"})
    conn.close()
    return jsonify({"status": "error", "message": "Unauthorized"}), 401

@app.route("/api/verify_2fa", methods=["POST"])
def verify_2fa():
    data = request.get_json()
    login = data.get("login")
    otp = data.get("otp")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT totp_secret, is_admin FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and user[1] and user[0] and pyotp.TOTP(user[0]).verify(otp):
        # генеруємо токен  session_token для адміна   /* ====================   Copyright © 2025 [DUDKA_ARTEM_ДУДКА_АРТЕМ_3676006734]. All rights reserved.) =========
        session_token = str(uuid.uuid4())
        cursor.execute("UPDATE users SET session_active = TRUE, session_token = %s WHERE login = %s", (session_token, login))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "session_token": session_token})
    conn.close()
    return jsonify({"status": "error", "message": "Invalid OTP"})

@app.route("/api/auth", methods=["POST"])
def auth():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, subscription_active, subscription_expires FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password):
        subscription_active = is_subscription_active(user[1], user[2])
        
        if subscription_active:
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

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, is_admin FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password) and user[1]:
        cursor.execute("SELECT login, password_hash, subscription_active, subscription_expires, created_at, session_active, session_token FROM users ORDER BY created_at DESC")
        users = []
        for row in cursor.fetchall():
            subscription_active = is_subscription_active(row[2], row[3])
            # підписочка гиги визначаємо тип 
            is_unlimited = row[2] and row[3] is None
            subscription_type = "unlimited" if is_unlimited else "temporary" if row[3] else "none"
            
            users.append({
                "login": row[0], 
                "password_hash": row[1], 
                "subscription_active": subscription_active,
                "subscription_expires": row[3].strftime("%Y-%m-%d %H:%M:%S") if row[3] else None,
                "subscription_type": subscription_type,
                "created_at": row[4], 
                "session_active": row[5], 
                "session_token": row[6]
            })
        conn.close()
        return jsonify({"status": "success", "users": users})
    conn.close()
    return jsonify({"status": "error", "message": "Невірні адмін-дані"}), 401

@app.route("/api/admin/update_subscription", methods=["POST"])
def update_subscription():
    data = request.get_json()
    login = data.get("login")
    password = data.get("password")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash, is_admin FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if user and check_password_hash(user[0], password) and user[1]:
        user_login = data.get("user_login")
        subscription_active = data.get("subscription_active")
        duration_hours = data.get("duration_hours", 0)  # 0 = скіки душа бажає на здоровля

        if subscription_active:
            if duration_hours > 0:
                expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
                cursor.execute("UPDATE users SET subscription_active = %s, subscription_expires = %s WHERE login = %s", 
                              (True, expires_at, user_login))
            else:
                # підписочка без терміну
                cursor.execute("UPDATE users SET subscription_active = %s, subscription_expires = NULL WHERE login = %s", 
                              (True, user_login))
        else:
            cursor.execute("UPDATE users SET subscription_active = %s, subscription_expires = NULL WHERE login = %s", 
                          (False, user_login))
        
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    conn.close()
    return jsonify({"status": "error", "message": "Невірні адмін-дані"}), 401

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
