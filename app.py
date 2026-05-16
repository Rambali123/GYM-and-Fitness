from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import mysql.connector
from datetime import date, timedelta

app = Flask(__name__)
app.secret_key = 'gympulse-secret-change-this'


# ── MySQL connection ─────────────────────────────────────────────────
def get_db():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='12345',
        database='gympulse'
    )


# ── Auth decorators ──────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ── Set admin password on first run ──────────────────────────────────
def init_admin():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT password_hash FROM users WHERE email='admin@gympulse.com'")
    row = cur.fetchone()
    if row and row[0].startswith('pbkdf2:sha256:600000$placeholder'):
        hashed = generate_password_hash('admin123')
        cur.execute("UPDATE users SET password_hash=%s WHERE email='admin@gympulse.com'", (hashed,))
        db.commit()
    cur.close()
    db.close()


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 1 — REGISTER & LOGIN (Scrum Master: Rambali)
# ══════════════════════════════════════════════════════════════════════

@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['full_name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        hashed = generate_password_hash(password)

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                "INSERT INTO users (full_name, email, phone, password_hash) VALUES (%s,%s,%s,%s)",
                (name, email, phone, hashed)
            )
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Email already registered.', 'danger')
        finally:
            cur.close()
            db.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        db.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['role'] = user['role']
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('member_dashboard'))
        flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════════════════════
#  MEMBER DASHBOARD & PROFILE (Scrum Master: Rambali)
# ══════════════════════════════════════════════════════════════════════

@app.route('/dashboard')
@login_required
def member_dashboard():
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("""
        SELECT s.*, mp.name AS plan_name, mp.price
        FROM subscriptions s
        JOIN membership_plans mp ON s.plan_id = mp.id
        WHERE s.user_id = %s ORDER BY s.end_date DESC LIMIT 1
    """, (session['user_id'],))
    subscription = cur.fetchone()

    cur.execute("""
        SELECT c.name, c.schedule_date, c.start_time, c.end_time,
               t.full_name AS trainer_name
        FROM class_registrations cr
        JOIN classes c ON cr.class_id = c.id
        LEFT JOIN trainers t ON c.trainer_id = t.id
        WHERE cr.user_id = %s AND c.schedule_date >= CURDATE()
        ORDER BY c.schedule_date, c.start_time
    """, (session['user_id'],))
    my_classes = cur.fetchall()

    cur.close()
    db.close()
    return render_template('member_dashboard.html',
                           subscription=subscription, my_classes=my_classes)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    cur = db.cursor(dictionary=True)

    if request.method == 'POST':
        cur.execute(
            "UPDATE users SET full_name=%s, phone=%s WHERE id=%s",
            (request.form['full_name'], request.form['phone'], session['user_id'])
        )
        db.commit()
        session['user_name'] = request.form['full_name']
        flash('Profile updated.', 'success')

    cur.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
    user = cur.fetchone()
    cur.close()
    db.close()
    return render_template('profile.html', user=user)


# ══════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD & MEMBERS (Scrum Master: Rambali)
# ══════════════════════════════════════════════════════════════════════

@app.route('/admin')
@admin_required
def admin_dashboard():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE role='member'")
    member_count = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM subscriptions WHERE status='active'")
    active_subs = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM classes WHERE schedule_date >= CURDATE()")
    upcoming = cur.fetchone()['cnt']
    cur.execute("SELECT COUNT(*) AS cnt FROM trainers")
    trainer_count = cur.fetchone()['cnt']
    cur.close()
    db.close()
    return render_template('admin_dashboard.html',
                           members=member_count, subs=active_subs,
                           upcoming=upcoming, trainers=trainer_count)


@app.route('/admin/members')
@admin_required
def admin_members():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT u.*, s.end_date, mp.name AS plan_name
        FROM users u
        LEFT JOIN subscriptions s ON u.id = s.user_id AND s.status='active'
        LEFT JOIN membership_plans mp ON s.plan_id = mp.id
        WHERE u.role = 'member'
        ORDER BY u.created_at DESC
    """)
    members = cur.fetchall()
    cur.close()
    db.close()
    return render_template('admin_members.html', members=members)


# ── Run ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_admin()
    app.run(debug=True)