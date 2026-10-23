import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, g, session, request, redirect, url_for, render_template, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "edubiblio-super-secret-key"
DATABASE = "library.db"

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, 
            role TEXT NOT NULL DEFAULT 'student', 
            name TEXT NOT NULL,
            class_name TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            title TEXT NOT NULL, 
            author TEXT NOT NULL,
            category TEXT NOT NULL,
            synopsis TEXT,
            cover_url TEXT,
            total_copies INTEGER NOT NULL DEFAULT 1, 
            available_copies INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            book_id INTEGER, 
            user_id INTEGER,
            borrowed_at TEXT, 
            due_date TEXT, 
            status TEXT DEFAULT 'ativo',
            FOREIGN KEY(book_id) REFERENCES books(id), 
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)
        
        # Cria o Admin se não existir
        if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            db.execute("INSERT INTO users (username,password_hash,role,name,class_name,created_at) VALUES (?,?,?,?,?,?)",
                ("admin", generate_password_hash("admin123"), "admin", "Administrador", "Coordenação", datetime.now().isoformat()))
            
            # Popula o banco com livros lindos pra ficar igual a sua imagem
            livros = [
                ("Dom Casmurro", "Machado de Assis", "Literatura Nacional", "Um clássico brasileiro sobre amor, ciúmes e a ambiguidade da inesquecível Capitu.", "https://images.unsplash.com/photo-1544947950-fa07a98d237f?q=80&w=800&auto=format&fit=crop", 3),
                ("O Pequeno Príncipe", "Antoine de Saint-Exupéry", "Literatura Estrangeira", "Uma poética história sobre amizade, amor e o essencial que é invisível aos olhos.", "https://images.unsplash.com/photo-1512820790803-83ca734da794?q=80&w=800&auto=format&fit=crop", 5),
                ("Sapiens: Uma Breve História", "Yuval Noah Harari", "História", "Uma jornada pela evolução da nossa espécie, da Idade da Pedra ao domínio da ciência.", "https://images.unsplash.com/photo-1532012197267-da84d127e765?q=80&w=800&auto=format&fit=crop", 2),
                ("Uma Breve História do Tempo", "Stephen Hawking", "Ciências", "Explorações sobre buracos negros, o Big Bang e o próprio tecido do universo.", "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800&auto=format&fit=crop", 2),
                ("O Alquimista", "Paulo Coelho", "Literatura Nacional", "A jornada mágica de Santiago em busca de um tesouro e do verdadeiro sentido da vida.", "https://images.unsplash.com/photo-1589829085413-56de8ae18c73?q=80&w=800&auto=format&fit=crop", 4),
                ("1984", "George Orwell", "Ficção Científica", "Um futuro distópico onde o Grande Irmão está sempre te observando e a verdade é reescrita.", "https://images.unsplash.com/photo-1495640388908-05fa85288e61?q=80&w=800&auto=format&fit=crop", 3)
            ]
            for title, author, cat, synopsis, url, copies in livros:
                db.execute("INSERT INTO books (title,author,category,synopsis,cover_url,total_copies,available_copies) VALUES (?,?,?,?,?,?,?)",
                           (title, author, cat, synopsis, url, copies, copies))
            
            # Cria um aluno de teste
            db.execute("INSERT INTO users (username,password_hash,role,name,class_name,created_at) VALUES (?,?,?,?,?,?)",
                ("lucas", generate_password_hash("123"), "student", "Lucas Oliveira", "9º Ano A", datetime.now().isoformat()))
            
        db.commit()

def current_user():
    return get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone() if "user_id" in session else None

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user(): return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        u = current_user()
        if not u or u["role"] != "admin":
            flash("Acesso restrito ao administrador.", "error")
            return redirect(url_for("dashboard"))
        return f(*a, **kw)
    return wrapper

@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user() else url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_db().execute("SELECT * FROM users WHERE username=?", (request.form["username"],)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Usuário ou senha incorretos.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user = current_user()
    
    if user["role"] == "admin":
        stats = {
            "livros": db.execute("SELECT COUNT(*) c FROM books").fetchone()["c"],
            "emprestimos": db.execute("SELECT COUNT(*) c FROM loans WHERE status='ativo'").fetchone()["c"],
            "alunos": db.execute("SELECT COUNT(*) c FROM users WHERE role='student'").fetchone()["c"],
        }
        return render_template("dashboard.html", user=user, stats=stats, is_admin=True)
    
    loans = db.execute("""
        SELECT l.*, b.title, b.author, b.cover_url 
        FROM loans l JOIN books b ON b.id=l.book_id 
        WHERE l.user_id=? AND l.status='ativo'
    """, (user["id"],)).fetchall()
    
    return render_template("dashboard.html", user=user, loans=loans, is_admin=False, now=datetime.now().isoformat())

@app.route("/catalog", methods=["GET", "POST"])
@login_required
def catalog():
    db = get_db()
    user = current_user()
    
    if request.method == "POST" and user["role"] == "student":
        book_id = request.form["book_id"]
        
        # Verifica limite de 3 livros
        if db.execute("SELECT COUNT(*) c FROM loans WHERE user_id=? AND status='ativo'", (user["id"],)).fetchone()["c"] >= 3:
            flash("Você já tem 3 empréstimos ativos. Devolva algum para pegar outro.", "error")
            return redirect(url_for("catalog"))
            
        # Verifica se o livro ta disponivel
        book = db.execute("SELECT available_copies FROM books WHERE id=?", (book_id,)).fetchone()
        if book and book["available_copies"] > 0:
            now = datetime.now()
            due = now + timedelta(days=14)
            db.execute("INSERT INTO loans (book_id,user_id,borrowed_at,due_date) VALUES (?,?,?,?)", 
                       (book_id, user["id"], now.isoformat(), due.isoformat()))
            db.execute("UPDATE books SET available_copies = available_copies - 1 WHERE id=?", (book_id,))
            db.commit()
            flash("Livro emprestado com sucesso! Prazo de 14 dias.", "success")
        else:
            flash("Livro indisponível no momento.", "error")
            
        return redirect(url_for("catalog"))

    # Filtros
    q = request.args.get("q", "")
    cat = request.args.get("category", "Todas as Categorias")
    
    sql = "SELECT * FROM books WHERE 1=1"
    params = []
    
    if q:
        sql += " AND (title LIKE ? OR author LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    if cat and cat != "Todas as Categorias":
        sql += " AND category = ?"
        params.append(cat)
        
    sql += " ORDER BY title"
    books = db.execute(sql, params).fetchall()
    
    # Pega categorias únicas pro filtro
    categories = [r["category"] for r in db.execute("SELECT DISTINCT category FROM books").fetchall()]
    
    # Pega os empréstimos do aluno pra saber o que já foi pego
    user_loans = [r["book_id"] for r in db.execute("SELECT book_id FROM loans WHERE user_id=? AND status='ativo'", (user["id"],)).fetchall()]
    
    return render_template("catalog.html", books=books, user=user, q=q, cat=cat, categories=categories, user_loans=user_loans)

@app.route("/return/<int:loan_id>", methods=["POST"])
@login_required
def return_loan(loan_id):
    db = get_db()
    loan = db.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
    if loan:
        db.execute("UPDATE loans SET status='devolvido' WHERE id=?", (loan_id,))
        db.execute("UPDATE books SET available_copies = available_copies + 1 WHERE id=?", (loan["book_id"],))
        db.commit()
        flash("Livro devolvido com sucesso!", "success")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "add_book":
            db.execute("""INSERT INTO books 
                (title, author, category, synopsis, cover_url, total_copies, available_copies) 
                VALUES (?,?,?,?,?,?,?)""", 
                (request.form["title"], request.form["author"], request.form["category"], 
                 request.form["synopsis"], request.form["cover_url"], 
                 request.form["copies"], request.form["copies"]))
            flash("Livro adicionado ao acervo!", "success")
            
        elif action == "add_user":
            try:
                db.execute("INSERT INTO users (username,password_hash,role,name,class_name,created_at) VALUES (?,?,?,?,?,?)",
                    (request.form["username"], generate_password_hash(request.form["password"]), "student", 
                     request.form["name"], request.form["class_name"], datetime.now().isoformat()))
                flash("Aluno cadastrado!", "success")
            except sqlite3.IntegrityError:
                flash("Este nome de usuário já existe.", "error")
                
        db.commit()
        return redirect(url_for("admin"))

    books = db.execute("SELECT * FROM books ORDER BY title").fetchall()
    users = db.execute("SELECT * FROM users WHERE role='student' ORDER BY name").fetchall()
    active_loans = db.execute("""
        SELECT l.*, b.title, u.name AS user_name, u.class_name 
        FROM loans l JOIN books b ON b.id=l.book_id JOIN users u ON u.id=l.user_id
        WHERE l.status='ativo' ORDER BY l.due_date
    """).fetchall()     
    return render_template("admin.html", books=books, users=users, loans=active_loans, now=datetime.now().isoformat(), user=current_user())

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)  