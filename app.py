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


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 3 — CLASS & ACTIVITY SCHEDULING (Developer: Binju)
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
#  SPRINT 4 — ASSIGN TRAINERS & TRACK HOURS (Developer: Binju)
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
    app.run(debug=True)