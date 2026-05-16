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
#  SPRINT 1 — REGISTER & LOGIN
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
#  MEMBER DASHBOARD & PROFILE
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
#  SPRINT 2 — MEMBERSHIP PLANS & BILLING
# ══════════════════════════════════════════════════════════════════════

@app.route('/plans')
@login_required
def plans():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM membership_plans")
    all_plans = cur.fetchall()
    cur.close()
    db.close()
    return render_template('plans.html', plans=all_plans)


@app.route('/subscribe/<int:plan_id>')
@login_required
def subscribe(plan_id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM membership_plans WHERE id=%s", (plan_id,))
    plan = cur.fetchone()
    if not plan:
        flash('Plan not found.', 'danger')
        return redirect(url_for('plans'))

    start = date.today()
    end = start + timedelta(days=plan['duration_days'])
    cur.execute(
        "INSERT INTO subscriptions (user_id, plan_id, start_date, end_date, paid) VALUES (%s,%s,%s,%s, TRUE)",
        (session['user_id'], plan_id, start, end)
    )
    db.commit()
    cur.close()
    db.close()
    flash(f'Subscribed to {plan["name"]}!', 'success')
    return redirect(url_for('member_dashboard'))


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 3 — CLASS & ACTIVITY SCHEDULING
# ══════════════════════════════════════════════════════════════════════

@app.route('/classes')
@login_required
def view_classes():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT c.*, t.full_name AS trainer_name,
               (SELECT COUNT(*) FROM class_registrations WHERE class_id = c.id) AS enrolled
        FROM classes c
        LEFT JOIN trainers t ON c.trainer_id = t.id
        WHERE c.schedule_date >= CURDATE()
        ORDER BY c.schedule_date, c.start_time
    """)
    classes = cur.fetchall()

    cur.execute("SELECT class_id FROM class_registrations WHERE user_id=%s",
                (session['user_id'],))
    my_ids = [r['class_id'] for r in cur.fetchall()]

    cur.close()
    db.close()
    return render_template('classes.html', classes=classes, my_ids=my_ids)


@app.route('/class/register/<int:class_id>')
@login_required
def register_class(class_id):
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM classes WHERE id=%s", (class_id,))
    cls = cur.fetchone()
    cur.execute("SELECT COUNT(*) AS cnt FROM class_registrations WHERE class_id=%s",
                (class_id,))
    count = cur.fetchone()['cnt']

    if count >= cls['max_capacity']:
        flash('Class is full.', 'warning')
    else:
        try:
            cur.execute(
                "INSERT INTO class_registrations (class_id, user_id) VALUES (%s,%s)",
                (class_id, session['user_id'])
            )
            db.commit()
            flash('Registered for class!', 'success')
        except mysql.connector.IntegrityError:
            flash('Already registered.', 'info')

    cur.close()
    db.close()
    return redirect(url_for('view_classes'))


@app.route('/class/cancel/<int:class_id>')
@login_required
def cancel_class(class_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM class_registrations WHERE class_id=%s AND user_id=%s",
                (class_id, session['user_id']))
    db.commit()
    cur.close()
    db.close()
    flash('Class registration cancelled.', 'info')
    return redirect(url_for('view_classes'))


# ══════════════════════════════════════════════════════════════════════
#  ADMIN DASHBOARD
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


# ── Admin: Members ───────────────────────────────────────────────────

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


# ── Admin: Plans ─────────────────────────────────────────────────────

@app.route('/admin/plans', methods=['GET', 'POST'])
@admin_required
def admin_plans():
    db = get_db()
    cur = db.cursor(dictionary=True)

    if request.method == 'POST':
        cur.execute(
            "INSERT INTO membership_plans (name, duration_days, price, description) VALUES (%s,%s,%s,%s)",
            (request.form['name'], request.form['duration_days'],
             request.form['price'], request.form['description'])
        )
        db.commit()
        flash('Plan added.', 'success')

    cur.execute("SELECT * FROM membership_plans")
    all_plans = cur.fetchall()
    cur.close()
    db.close()
    return render_template('admin_plans.html', plans=all_plans)


@app.route('/admin/plan/delete/<int:plan_id>')
@admin_required
def delete_plan(plan_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM membership_plans WHERE id=%s", (plan_id,))
    db.commit()
    cur.close()
    db.close()
    flash('Plan deleted.', 'info')
    return redirect(url_for('admin_plans'))


# ── Admin: Classes (Sprint 3) ────────────────────────────────────────

@app.route('/admin/classes', methods=['GET', 'POST'])
@admin_required
def admin_classes():
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM trainers")
    trainers = cur.fetchall()

    if request.method == 'POST':
        trainer_id = request.form['trainer_id'] or None
        cur.execute(
            """INSERT INTO classes (name, description, trainer_id, schedule_date,
               start_time, end_time, max_capacity)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (request.form['name'], request.form['description'],
             trainer_id, request.form['schedule_date'],
             request.form['start_time'], request.form['end_time'],
             request.form['max_capacity'])
        )
        db.commit()
        flash('Class added.', 'success')

    cur.execute("""
        SELECT c.*, t.full_name AS trainer_name,
               (SELECT COUNT(*) FROM class_registrations WHERE class_id=c.id) AS enrolled
        FROM classes c
        LEFT JOIN trainers t ON c.trainer_id = t.id
        ORDER BY c.schedule_date DESC
    """)
    classes = cur.fetchall()
    cur.close()
    db.close()
    return render_template('admin_classes.html', classes=classes, trainers=trainers)


@app.route('/admin/class/delete/<int:class_id>')
@admin_required
def delete_class(class_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM class_registrations WHERE class_id=%s", (class_id,))
    cur.execute("DELETE FROM trainer_hours WHERE class_id=%s", (class_id,))
    cur.execute("DELETE FROM classes WHERE id=%s", (class_id,))
    db.commit()
    cur.close()
    db.close()
    flash('Class deleted.', 'info')
    return redirect(url_for('admin_classes'))


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 4 — ASSIGN TRAINERS & TRACK HOURS
# ══════════════════════════════════════════════════════════════════════

@app.route('/admin/trainers', methods=['GET', 'POST'])
@admin_required
def admin_trainers():
    db = get_db()
    cur = db.cursor(dictionary=True)

    if request.method == 'POST':
        cur.execute(
            "INSERT INTO trainers (full_name, specialisation, phone, hourly_rate) VALUES (%s,%s,%s,%s)",
            (request.form['full_name'], request.form['specialisation'],
             request.form['phone'], request.form['hourly_rate'])
        )
        db.commit()
        flash('Trainer added.', 'success')

    cur.execute("SELECT * FROM trainers ORDER BY full_name")
    trainers = cur.fetchall()
    cur.close()
    db.close()
    return render_template('admin_trainers.html', trainers=trainers)


@app.route('/admin/trainer/delete/<int:trainer_id>')
@admin_required
def delete_trainer(trainer_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE classes SET trainer_id=NULL WHERE trainer_id=%s", (trainer_id,))
    cur.execute("DELETE FROM trainer_hours WHERE trainer_id=%s", (trainer_id,))
    cur.execute("DELETE FROM trainers WHERE id=%s", (trainer_id,))
    db.commit()
    cur.close()
    db.close()
    flash('Trainer removed.', 'info')
    return redirect(url_for('admin_trainers'))


@app.route('/admin/hours', methods=['GET', 'POST'])
@admin_required
def admin_hours():
    db = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute("SELECT * FROM trainers ORDER BY full_name")
    trainers = cur.fetchall()
    cur.execute("SELECT id, name, schedule_date FROM classes ORDER BY schedule_date DESC")
    classes = cur.fetchall()

    if request.method == 'POST':
        cur.execute(
            "INSERT INTO trainer_hours (trainer_id, class_id, hours_worked, log_date) VALUES (%s,%s,%s,%s)",
            (request.form['trainer_id'], request.form['class_id'],
             request.form['hours_worked'], request.form['log_date'])
        )
        db.commit()
        flash('Hours logged.', 'success')

    cur.execute("""
        SELECT th.*, t.full_name AS trainer_name, c.name AS class_name
        FROM trainer_hours th
        JOIN trainers t ON th.trainer_id = t.id
        JOIN classes c ON th.class_id = c.id
        ORDER BY th.log_date DESC
    """)
    logs = cur.fetchall()

    cur.execute("""
        SELECT t.full_name, SUM(th.hours_worked) AS total_hours,
               t.hourly_rate, SUM(th.hours_worked) * t.hourly_rate AS total_pay
        FROM trainer_hours th
        JOIN trainers t ON th.trainer_id = t.id
        GROUP BY t.id
    """)
    summary = cur.fetchall()

    cur.close()
    db.close()
    return render_template('admin_hours.html', trainers=trainers,
                           classes=classes, logs=logs, summary=summary)


# ── Run ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_admin()
    app.run(debug=True)