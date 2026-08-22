from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, send_file, abort
import pyodbc
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import shutil
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")


UPLOAD_FOLDER_GAMES = "static/uploads/games"
UPLOAD_FOLDER_IMAGES = "static/uploads/images"
APPROVED_FOLDER = "static/uploads/approved"


for folder in [UPLOAD_FOLDER_GAMES, UPLOAD_FOLDER_IMAGES, APPROVED_FOLDER]:
    os.makedirs(folder, exist_ok=True)


ALLOWED_GAME_EXTENSIONS = {'zip', 'exe', 'rar'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename, allowed_ext):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_ext


conn = pyodbc.connect(os.getenv("DB_CONNECTION_STRING"))
cursor = conn.cursor()

@app.route('/')
def home():
    if session.get('username'):
        cursor.execute("SELECT game_id, title, description, price, release_date, developer, image_url FROM Games WHERE status='approved'")
        games_list = cursor.fetchall()
        games = []
        for g in games_list:
            games.append({
                'id': g.game_id,
                'title': g.title,
                'description': g.description,
                'price': g.price,
                'release_date': g.release_date,
                'developer': g.developer,
                'image': g.image_url or 'uploads/images/default_game.png'
            })
        return render_template('index.html', games=games)
    
    return redirect(url_for('login'))

class Game:
    def __init__(self, g):
        self.id = g.game_id
        self.title = g.title
        self.description = g.description
        self.price = g.price
        self.release_date = g.release_date
        self.developer = g.developer
        self.image = g.image_url or f'static/images/games/game{g.game_id}.jpg'
       
        self.system_requirements = getattr(g, 'system_requirements', '')
        self.screenshots = getattr(g, 'screenshots', '')

@app.route("/upload-game", methods=['GET', 'POST'])
def upload_game():
    if 'username' not in session:
        return redirect(url_for('login'))

    error = None
    success = None

    if request.method == "POST":
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        price = float(request.form.get('price', 0))
        developer = session['username']
        system_req = request.form.get('system_requirements', '')
        release_date = datetime.now()

        game_file = request.files.get('game_file')
        image_file = request.files.get('image_file')

        if not title or not description or not game_file:
            error = "Пожалуйста, заполните все обязательные поля и выберите файл игры."
        elif not allowed_file(game_file.filename, ALLOWED_GAME_EXTENSIONS):
            error = "Недопустимый формат файла игры."
        elif image_file and not allowed_file(image_file.filename, ALLOWED_IMAGE_EXTENSIONS):
            error = "Недопустимый формат обложки."
        else:
            
            game_filename = secure_filename(f"{datetime.now().timestamp()}_{game_file.filename}")
            game_path = os.path.join(UPLOAD_FOLDER_GAMES, game_filename)
            game_file.save(game_path)

         
            if image_file and image_file.filename:
                image_filename = secure_filename(f"{datetime.now().timestamp()}_{image_file.filename}")
                image_path = os.path.join(UPLOAD_FOLDER_IMAGES, image_filename)
                image_file.save(image_path)
               
                image_db_path = f"uploads/images/{image_filename}"
            else:
                image_db_path = "images/default_game.png"  

            
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Games 
                (title, description, price, release_date, developer, image_url, system_requirements, file_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title,
                description,
                price,
                release_date,
                developer,
                image_db_path,
                system_req,
                game_path.replace("\\", "/"),
                "pending"
            ))
            conn.commit()
            success = "Игра успешно загружена! Она появится после проверки администратором."

    return render_template("upload_game.html", error=error, success=success)


@app.route("/pending-game/<int:game_id>")
def pending_game(game_id):
    if session.get("role") != "admin":
        return "Доступ запрещен", 403

    cursor = conn.cursor()
    
    cursor.execute("SELECT game_id, title, description, price, image_url, file_path FROM Games WHERE status='pending'")
    rows = cursor.fetchall()
    pending_games = []
    for g in rows:
        pending_games.append({
            "game_id": g[0],
            "title": g[1],
            "description": g[2],
            "price": g[3],
            "image": g[4] if g[4] else "images/default_game.png",
            "file_path": g[5]  
        })

  
    selected_game = next((g for g in pending_games if g["game_id"] == game_id), None)

    return render_template("pending_games.html", games=pending_games, selected_game=selected_game)

@app.route("/pending-games")
def pending_games_page():
    if session.get("role") != "admin":
        return "Доступ запрещен", 403

    cursor = conn.cursor()
    cursor.execute("SELECT game_id, title, description, price, image_url, file_path FROM Games WHERE status='pending'")
    rows = cursor.fetchall()

    pending_games = []
    for g in rows:
        pending_games.append({
            "game_id": g[0],
            "title": g[1],
            "description": g[2],
            "price": g[3],
            "image": g[4] if g[4] else "images/default_game.png",
            "file_path": g[5]  
        })

   
    selected_game = None

    return render_template("pending_games.html", games=pending_games, selected_game=selected_game)

@app.route("/approve-game/<int:game_id>")
def approve_game(game_id):
    if session.get("role") != "admin":
        return "Доступ запрещен", 403

    cursor = conn.cursor()
    cursor.execute("SELECT file_path, image_url FROM Games WHERE game_id=?", (game_id,))
    game = cursor.fetchone()
    if not game:
        return "Игра не найдена", 404

    game_file_path, image_url = game

    
    if not os.path.exists(game_file_path):
        return f"Файл игры не найден: {game_file_path}", 404

    approved_game_path = os.path.join(APPROVED_FOLDER, os.path.basename(game_file_path))
    shutil.move(game_file_path, approved_game_path)

    if image_url != "images/default_game.png":
        old_image_path = os.path.join("static", image_url)
        if os.path.exists(old_image_path):
            approved_image_filename = os.path.basename(old_image_path)
            approved_image_path = os.path.join(APPROVED_FOLDER, approved_image_filename)
            shutil.move(old_image_path, approved_image_path)
            approved_image_db = f"uploads/approved/{approved_image_filename}"
        else:
            approved_image_db = "images/default_game.png"
    else:
        approved_image_db = "images/default_game.png"

    cursor.execute(
        "UPDATE Games SET status='approved', file_path=?, image_url=? WHERE game_id=?",
        (approved_game_path.replace("\\", "/"), approved_image_db, game_id)
    )
    conn.commit()
    return redirect(url_for("pending_games_page"))

@app.route("/reject-game/<int:game_id>")
def reject_game(game_id):
    if session.get("role") != "admin":
        return "Доступ запрещен", 403

    cursor = conn.cursor()
    cursor.execute("SELECT file_path, image_url FROM Games WHERE game_id=?", (game_id,))
    game = cursor.fetchone()
    if not game:
        return "Игра не найдена", 404

    
    if os.path.exists(game[0]):
        os.remove(game[0])
    if game[1] and os.path.exists(game[1]):
        os.remove(game[1])

    cursor.execute("DELETE FROM Games WHERE game_id=?", (game_id,))
    conn.commit()
    return redirect(url_for("pending_games_page"))


@app.route('/games')
def games_page():
    cursor.execute("SELECT game_id, title, description, price, release_date, developer, image_url FROM Games WHERE status='approved'")
    games_list = cursor.fetchall()
    games = [Game(g) for g in games_list]
    return render_template('games.html', games=games)

@app.route("/store/<int:game_id>")
def store_game(game_id):
    if not session.get("username"):
        return redirect(url_for("login"))

    cursor = conn.cursor()
    cursor.execute("""
        SELECT game_id, title, description, price, developer, release_date, image_url, system_requirements
        FROM Games
        WHERE game_id=?
    """, (game_id,))
    game = fetchone_dict(cursor)

    if not game:
        return "Игра не найдена", 404

    
    if not game.get('image_url'):
        game['image'] = f'static/images/games/game{game["game_id"]}.jpg'
    else:
        game['image'] = game['image_url']

    return render_template("store.html", game=game)


@app.route("/buy/<int:game_id>", methods=['POST'])
def buy_game(game_id):
    if not session.get('id'):
        return redirect(url_for('login'))

    user_id = session['id']
    cursor = conn.cursor()

   
    cursor.execute("SELECT price FROM Games WHERE game_id=?", (game_id,))
    game = cursor.fetchone()

    if not game:
        return "Игра не найдена", 404

    price = float(game[0])

   
    cursor.execute("SELECT * FROM purchases WHERE user_id=? AND game_id=?", (user_id, game_id))
    if cursor.fetchone():
        return "Вы уже купили эту игру"

   
    if price == 0:
        cursor.execute("INSERT INTO purchases (user_id, game_id, purchase_date) VALUES (?, ?, GETDATE())",
                       (user_id, game_id))
        conn.commit()
        return redirect(url_for('library'))

   
    cursor.execute("SELECT balance FROM Users WHERE id=?", (user_id,))
    balance = float(cursor.fetchone()[0])

    if balance < price:
        return "Недостаточно средств"

    new_balance = balance - price
    cursor.execute("UPDATE Users SET balance=? WHERE id=?", (new_balance, user_id))

    cursor.execute("INSERT INTO purchases (user_id, game_id, purchase_date) VALUES (?, ?, GETDATE())",
                   (user_id, game_id))

    conn.commit()

    
    session['balance'] = new_balance

    return redirect(url_for('library'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
       

       
        cursor.execute("SELECT id FROM Users WHERE username=?", (username,))
        if cursor.fetchone():
            return render_template('register.html', error="Имя пользователя занято")

       
        default_avatar = 'images/users/default15253526215.png'

        password_hash = generate_password_hash(password)
       
        cursor.execute(
            """
            INSERT INTO Users (username, email, password_hash, avatar_url, balance)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, email, password_hash, default_avatar, 0)
        )
        session['avatar'] = default_avatar
        conn.commit()

        cursor.execute("SELECT id FROM Users WHERE username=?", (username,))
        new_user_id = cursor.fetchone()[0]

        session['username'] = username
        session['id'] = new_user_id
        session['avatar'] = default_avatar
        session['balance'] = 0
        session['role'] = 'user'

        return redirect(url_for('home'))

    return render_template('register.html')


@app.route('/community')
def community():
    
    cursor.execute("""
        SELECT t.topic_id, t.title, u.username, t.created_at
        FROM Topics t
        JOIN Users u ON t.creator_id = u.id
        ORDER BY t.created_at DESC
    """)
    topics_list = cursor.fetchall()
    topics = []
    for t in topics_list:
        topics.append({
            'id': t.topic_id,
            'title': t.title,
            'creator': t.username,
            'created_at': t.created_at
        })
    return render_template('community.html', topics=topics)

@app.route('/community/new', methods=['GET', 'POST'])
def new_topic():
    if not session.get('username'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        creator_id = session['id']

        cursor.execute("INSERT INTO Topics (title, creator_id) VALUES (?, ?)", (title, creator_id))
        conn.commit()
        return redirect(url_for('community'))

    return render_template('new_topic.html')


@app.route('/community/topic/<int:topic_id>', methods=['GET', 'POST'])
def view_topic(topic_id):
    if request.method == 'POST':
        if not session.get('username'):
            return redirect(url_for('login'))

        content = request.form['content']
        user_id = session['id']
        cursor.execute("INSERT INTO Messages (topic_id, user_id, content) VALUES (?, ?, ?)",
                       (topic_id, user_id, content))
        conn.commit()
        return redirect(url_for('view_topic', topic_id=topic_id))


    cursor.execute("""
        SELECT t.topic_id, t.title, u.username, t.created_at
        FROM Topics t
        JOIN Users u ON t.creator_id = u.id
        WHERE t.topic_id=?
    """, (topic_id,))
    topic = cursor.fetchone()

  
    cursor.execute("""
        SELECT m.content, u.username, m.created_at
        FROM Messages m
        JOIN Users u ON m.user_id = u.id
        WHERE m.topic_id=?
        ORDER BY m.created_at ASC
    """, (topic_id,))
    messages_list = cursor.fetchall()
    messages = []
    for m in messages_list:
        messages.append({
            'content': m.content,
            'author': m.username,
            'created_at': m.created_at
        })

    return render_template('topic.html', topic=topic, messages=messages)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor.execute("""
            SELECT id, username, avatar_url, balance, role, password_hash
            FROM Users 
            WHERE username=?
        """, (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user[5], password):
            session['id'] = user[0]
            session['username'] = user[1]
            session['avatar'] = user[2]
            session['balance'] = float(user[3])
            session['role'] = user[4]  

            print("Login role:", session['role']) 
            return redirect(url_for('home'))

        return render_template('login.html', error="Неверный логин или пароль")

    return render_template('login.html')

def fetchall_dict(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def fetchone_dict(cursor):
    row = cursor.fetchone()
    if row:
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))
    return None



# downnn
















@app.route('/api/add_to_library/<int:game_id>', methods=['POST'])
def add_to_library(game_id):
    if 'id' not in session:
        return jsonify({"error": "Не авторизован"}), 401

    user_id = session['id']
    cursor = conn.cursor()


    cursor.execute("SELECT * FROM purchases WHERE user_id=? AND game_id=?", (user_id, game_id))
    if cursor.fetchone():
        return jsonify({"message": "Игра уже есть в вашей библиотеке"})

   
    cursor.execute("SELECT price FROM Games WHERE game_id=?", (game_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({"error": "Игра не найдена"}), 404
    price = row[0]

    if price > 0:
        return jsonify({"error": "Эта игра платная"}), 400


    cursor.execute("INSERT INTO purchases (user_id, game_id, purchase_date) VALUES (?, ?, GETDATE())",
                   (user_id, game_id))
    conn.commit()

    return jsonify({"message": "Игра успешно добавлена в библиотеку"})


@app.route('/api/my-games')
def api_my_games():
    if not session.get("id"):
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session.get("id")

    cursor.execute("""
        SELECT g.game_id, g.title, g.file_path
        FROM Games g
        JOIN purchases p ON g.game_id = p.game_id
        WHERE p.user_id = ?
    """, (user_id,))

    games = fetchall_dict(cursor)
    return jsonify(games)




@app.route("/library")
def library():
    if not session.get("username"):
        return redirect(url_for("login"))

    user_id = session.get("id")  
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.game_id, g.title, g.image_url
        FROM Games g
        JOIN purchases p ON g.game_id = p.game_id
        WHERE p.user_id = ?
    """, (user_id,))
    games = fetchall_dict(cursor)

    return render_template("library.html", games=games, selected_game=None)



@app.route("/library/<int:game_id>")
def library_game(game_id):
    if not session.get("username"):
        return redirect(url_for("login"))

    user_id = session.get("id")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT g.game_id, g.title, g.image_url, g.description
        FROM Games g
        JOIN purchases p ON g.game_id = p.game_id
        WHERE g.game_id=? AND p.user_id=?
    """, (game_id, user_id))
    selected_game = fetchone_dict(cursor)

    cursor.execute("""
        SELECT g.game_id, g.title, g.image_url
        FROM Games g
        JOIN purchases p ON g.game_id = p.game_id
        WHERE p.user_id = ?
    """, (user_id,))
    games = fetchall_dict(cursor)

    return render_template("library.html", games=games, selected_game=selected_game)






@app.route("/download/<int:game_id>")
def download_game(game_id):
    if not session.get('username'):
        return redirect(url_for('login'))

    user_id = session['id']
    cursor = conn.cursor()

    if session.get('role') == 'admin':
        cursor.execute("SELECT file_path, title FROM Games WHERE game_id=?", (game_id,))
    else:
        cursor.execute("""
            SELECT g.file_path, g.title 
            FROM Games g
            JOIN Purchases p ON g.game_id = p.game_id
            WHERE g.game_id=? AND p.user_id=?
        """, (game_id, user_id))

    row = cursor.fetchone()

    if not row:
        abort(404, "Игра не найдена или не куплена")

    file_path, title = row

    if not os.path.exists(file_path):
        abort(404, "Файл игры не найден на сервере")

    return send_file(file_path, as_attachment=True, download_name=f"{title}.zip")


@app.route('/profile')
def profile():
    if not session.get('id'):
        return redirect(url_for('login'))

    cursor.execute("SELECT username, avatar_url, balance FROM Users WHERE id=?", (session['id'],))
    row = cursor.fetchone()
    if not row:
        return redirect(url_for('logout'))

    user_data = {
        'username': row.username,
        'avatar': row.avatar_url or 'static/images/default15253526215.png',
        'balance': row.balance
    }


    cursor.execute("""
    SELECT g.game_id, g.title, g.image_url
    FROM Purchases p
    JOIN Games g ON p.game_id = g.game_id
    WHERE p.user_id = ?
""", (session['id'],))  
    purchased_games_list = cursor.fetchall()
    user_games = []

    for game in purchased_games_list:
        user_games.append({
            'id': game.game_id,
            'name': game.title,
            'image': url_for('static', filename=game.image_url.replace('static/', '')) 
                     if game.image_url else url_for('static', filename='uploads/images/default_game.png')
        })

    return render_template('profile.html', user=user_data, user_items=user_games)


@app.context_processor
def inject_user():
    if session.get('id'):
        cursor.execute("SELECT username, avatar_url, balance FROM Users WHERE id=?", (session['id'],))
        row = cursor.fetchone()
        if row:
            return dict(user={
                'username': row.username,
                'avatar': row.avatar_url or 'static/images/default15253526215.png',
                'balance': row.balance
            })
    return dict(user=None)


@app.route('/add_balance', methods=['GET', 'POST'])
def add_balance():
    if 'id' not in session:
        return redirect(url_for('login'))

    error = None

    if request.method == 'POST':
        amount_str = request.form.get('amount', '').strip()
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0
            error = "Введите корректное число"

        if amount <= 0:
            error = "Сумма должна быть больше нуля"

        if not error:
            cursor.execute("UPDATE Users SET balance = balance + ? WHERE id = ?", (amount, session['id']))
            conn.commit()
            session['balance'] = float(session.get('balance', 0)) + amount

            return redirect(url_for('profile'))

    return render_template('add_balance.html', error=error)








@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'id' not in session:
        return redirect(url_for('login'))

    user_id = session['id']

    conn_local = pyodbc.connect(os.getenv("DB_CONNECTION_STRING"))
    cursor = conn_local.cursor()

    if request.method == 'POST':
        new_username = request.form['username']
        new_email = request.form['email']
        avatar_file = request.files.get('avatar')

        cursor.execute(
            "SELECT id FROM Users WHERE username = ? AND id != ?",
            (new_username, user_id)
        )

        if cursor.fetchone():
            cursor.execute(
                "SELECT username, email, avatar_url FROM Users WHERE id=?",
                (user_id,)
            )
            row = cursor.fetchone()

            cursor.close()
            conn_local.close()

            return render_template(
                "edit_profile.html",
                user={"username": row[0], "email": row[1], "avatar_url": row[2]},
                error="Этот никнейм уже занят"
            )

        avatar_path = None

        if avatar_file and avatar_file.filename:
            filename = secure_filename(avatar_file.filename)
            avatar_path = f"static/images/users/{user_id}_{filename}"
            avatar_file.save(avatar_path)

        if avatar_path:
            cursor.execute("""
                UPDATE Users
                SET username=?, email=?, avatar_url=?
                WHERE id=?
            """, (new_username, new_email, avatar_path, user_id))
            session['avatar'] = avatar_path
        else:
            cursor.execute("""
                UPDATE Users
                SET username=?, email=?
                WHERE id=?
            """, (new_username, new_email, user_id))

        conn_local.commit()
        cursor.close()
        conn_local.close()

        session['username'] = new_username
        return redirect(url_for('profile'))

    cursor.execute("SELECT username, email, avatar_url FROM Users WHERE id=?", (user_id,))
    row = cursor.fetchone()

    cursor.close()
    conn_local.close()

    user = {
        "username": row[0],
        "email": row[1],
        "avatar_url": row[2]
    }

    return render_template("edit_profile.html", user=user)




@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)
