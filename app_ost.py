from flask import Flask, request, jsonify, render_template_string
import psycopg2
import hashlib
import os
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# Database connection
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://passport_reader_db_o2k5_user:mwa8s07Ozmr3rk4l3Gd3QZhitUCbVlpo@dpg-d1b7mjbe5dus73ealib0-a.oregon-postgres.render.com/passport_reader_db_o2k5')
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# HTML template with Tailwind CSS and animations
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Passport Reader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        .btn-animated:hover {
            animation: pulse 0.3s ease-in-out;
            background-color: #10b981;
        }
        .loading::after {
            content: '';
            display: inline-block;
            width: 1rem;
            height: 1rem;
            border: 2px solid #fff;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-left: 0.5rem;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body class="bg-gray-100 flex flex-col items-center justify-center min-h-screen font-sans">
    <div class="bg-white p-8 rounded-lg shadow-lg w-full max-w-md">
        <h1 class="text-3xl font-bold text-center text-teal-600 mb-6">{{ title }}</h1>
        {% if message %}
            <p class="text-center text-red-500 mb-4">{{ message }}</p>
        {% endif %}
        {{ content | safe }}
    </div>
</body>
</html>
"""

# Login page
@app.route('/')
def login_page():
    content = """
        <form action="/api/auth" method="POST" class="space-y-4">
            <div>
                <label for="login" class="block text-lg font-medium text-gray-700">Логін</label>
                <input type="text" name="login" id="login" required class="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-teal-500 focus:border-teal-500">
            </div>
            <div>
                <label for="password" class="block text-lg font-medium text-gray-700">Пароль</label>
                <input type="password" name="password" id="password" required class="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-teal-500 focus:border-teal-500">
            </div>
            <button type="submit" class="w-full bg-teal-600 text-white text-lg font-semibold py-3 px-6 rounded-lg btn-animated hover:bg-teal-700 transition duration-300">Увійти</button>
        </form>
        <p class="mt-4 text-center"><a href="/admin" class="text-teal-600 hover:underline">Адмін-панель</a></p>
    """
    return render_template_string(HTML_TEMPLATE, title="Вхід", content=content)

# Authentication API
@app.route('/api/auth', methods=['POST'])
def authenticate():
    data = request.get_json() or request.form
    login = data.get('login')
    password = data.get('password')

    if not login or not password:
        return jsonify({"status": "error", "message": "Логін і пароль обов'язкові"})

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute("SELECT password_hash, subscription_active, session_active, subscription_end FROM users WHERE login = %s", (login,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"status": "error", "message": "Невірний логін"})

    db_password_hash, subscription_active, session_active, subscription_end = user

    if password_hash != db_password_hash:
        return jsonify({"status": "error", "message": "Невірний пароль"})

    if not subscription_active or (subscription_end and subscription_end < datetime.now(pytz.UTC)):
        return jsonify({"status": "error", "message": "Підписка неактивна або закінчилася"})

    if session_active:
        return jsonify({"status": "error", "message": "Сесія вже активна на іншому пристрої"})

    cursor.execute("UPDATE users SET session_active = TRUE, device_id = %s WHERE login = %s", (request.remote_addr, login))
    conn.commit()

    return jsonify({"status": "success", "subscription_active": True})

# Logout API
@app.route('/api/logout', methods=['POST'])
def logout():
    data = request.get_json() or request.form
    login = data.get('login')
    if login:
        cursor.execute("UPDATE users SET session_active = FALSE, device_id = NULL WHERE login = %s", (login,))
        conn.commit()
    return jsonify({"status": "success"})

# Admin panel
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    ADMIN_LOGIN = "admin"
    ADMIN_PASSWORD = "admin123"

    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        action = request.form.get('action')
        user_login = request.form.get('user_login')
        duration = request.form.get('duration')

        if login == ADMIN_LOGIN and password == ADMIN_PASSWORD:
            if action == "view":
                cursor.execute("SELECT login, subscription_active, subscription_end, session_active FROM users")
                users = cursor.fetchall()
                user_list = "".join([f"<li class='py-2'>Логін: {u[0]}, Підписка: {'Активна' if u[1] else 'Неактивна'}, Закінчення: {u[2] or 'Немає'}, Сесія: {'Активна' if u[3] else 'Неактивна'}</li>" for u in users])
                content = f"""
                    <h2 class="text-2xl font-semibold text-teal-600 mb-4">Список користувачів</h2>
                    <ul class="list-disc pl-5">{user_list}</ul>
                    <h2 class="text-2xl font-semibold text-teal-600 mt-6 mb-4">Активувати підписку</h2>
                    <form action="/admin" method="POST" class="space-y-4">
                        <input type="hidden" name="login" value="{login}">
                        <input type="hidden" name="password" value="{password}">
                        <input type="hidden" name="action" value="activate">
                        <div>
                            <label for="user_login" class="block text-lg font-medium text-gray-700">Логін користувача</label>
                            <input type="text" name="user_login" id="user_login" required class="mt-1 w-full p-3 border border-gray-300 rounded-lg">
                        </div>
                        <div>
                            <label for="duration" class="block text-lg font-medium text-gray-700">Тривалість підписки</label>
                            <select name="duration" id="duration" class="mt-1 w-full p-3 border border-gray-300 rounded-lg">
                                <option value="6">6 годин</option>
                                <option value="24">24 години</option>
                                <option value="48">48 години</option>
                                <option value="720">720 годин (30 днів)</option>
                            </select>
                        </div>
                        <button type="submit" class="w-full bg-teal-600 text-white text-lg font-semibold py-3 px-6 rounded-lg btn-animated hover:bg-teal-700 transition duration-300">Активувати</button>
                    </form>
                    <p class="mt-4 text-center"><a href="/" class="text-teal-600 hover:underline">Назад до входу</a></p>
                """
                return render_template_string(HTML_TEMPLATE, title="Адмін-панель", content=content)

            elif action == "activate" and user_login and duration:
                cursor.execute("SELECT login FROM users WHERE login = %s", (user_login,))
                if not cursor.fetchone():
                    return render_template_string(HTML_TEMPLATE, title="Адмін-панель", content="<p class='text-red-500'>Користувача не знайдено</p>", message="Помилка")
                
                duration_hours = int(duration)
                end_time = datetime.now(pytz.UTC) + timedelta(hours=duration_hours)
                cursor.execute("UPDATE users SET subscription_active = TRUE, subscription_end = %s WHERE login = %s", (end_time, user_login))
                conn.commit()
                return render_template_string(HTML_TEMPLATE, title="Адмін-панель", content="<p class='text-green-500'>Підписку активовано!</p>", message="Успіх")
        
        return render_template_string(HTML_TEMPLATE, title="Адмін-панель", content="<p class='text-red-500'>Невірний логін або пароль</p>", message="Помилка")

    content = """
        <form action="/admin" method="POST" class="space-y-4">
            <input type="hidden" name="action" value="view">
            <div>
                <label for="login" class="block text-lg font-medium text-gray-700">Логін адміна</label>
                <input type="text" name="login" id="login" required class="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-teal-500 focus:border-teal-500">
            </div>
            <div>
                <label for="password" class="block text-lg font-medium text-gray-700">Пароль адміна</label>
                <input type="password" name="password" id="password" required class="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-teal-500 focus:border-teal-500">
            </div>
            <button type="submit" class="w-full bg-teal-600 text-white text-lg font-semibold py-3 px-6 rounded-lg btn-animated hover:bg-teal-700 transition duration-300">Увійти</button>
        </form>
        <p class="mt-4 text-center"><a href="/" class="text-teal-600 hover:underline">Назад до входу</a></p>
    """
    return render_template_string(HTML_TEMPLATE, title="Адмін-панель", content=content)

# User account page
@app.route('/account', methods=['GET', 'POST'])
def account_page():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')

        if not login or not password:
            return render_template_string(HTML_TEMPLATE, title="Акаунт", content="<p class='text-red-500'>Логін і пароль обов'язкові</p>", message="Помилка")

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute("SELECT password_hash, subscription_active, subscription_end, session_active FROM users WHERE login = %s", (login,))
        user = cursor.fetchone()

        if not user or password_hash != user[0]:
            return render_template_string(HTML_TEMPLATE, title="Акаунт", content="<p>" + ("Невірний логін" if user else "Невірний пароль") + "</p>", message="Помилка")

        subscription_active, subscription_end, session_active = user[1:]
        now = datetime.now(pytz.UTC)
        status = "Активна" if subscription_active else "Неактивна"
        remaining_time = ""
        if subscription_active and subscription_end and subscription_end > now:
            remaining_seconds = (remaining_end - remaining_now).total_seconds()
            remaining_hours = int(remaining_seconds // 3600)
            remaining_minutes = int((remaining_seconds % 3600) // 60)
            remaining_time = f"Залишилось: {remaining_hours} год, {remaining_minutes} хв"
            end_date = subscription_end.strftime("%Y-%m-%d %H:%M:%S")
        else:
            remaining_time = "Підписка закінчена"
            end_date = ""

        content = f"""
            <h2 class="text-2xl font-semibold text-teal-600 mb-4">Ваш акаунт</h2>
            <p class="text-lg">Логін: {login}</p>
            <p class="text-lg">Статус підписки: {status}</p>
            <p class="text-lg">Закінчення підписки: {end_date or 'Немає'}</p>
            <p class="text-lg">{remaining_time}</p>
            <p class="mt-4 text-center"><a href="/" class="text-teal-600 hover:underline">Назад до входу</a></p>
        """
        return render_template_string(HTML_TEMPLATE, title="Акаунт", content=content)

    content = """
        <form action="/account" method="POST" class="space-y-4">
            <div>
                <label for="login" class="block text-lg font-medium text-gray-700">Логін</label>
                <input type="text" name="login" id="login" required class="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-teal-500 focus:border-teal-500">
            </div>
            <div>
                <label for="password" class="block text-lg font-medium text-gray-700">Пароль</label>
                <input type="password" name="password" id="password" required class="mt-1 w-full p-3 border border-gray-300 rounded-lg focus:ring-teal-500 focus:border-teal-500">
            </div>
            <button type="submit" class="w-full bg-teal-600 text-white text-lg font-semibold py-3 px-6 rounded-lg btn-animated hover:bg-teal-700 transition duration-300">Переглянути акаунт</button>
        </form>
        <p class="mt-4 text-center"><a href="/" class="text-teal-600 hover:underline">Назад до входу</a></p>
    """
    return render_template_string(HTML_TEMPLATE, title="Акаунт", content=content)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
