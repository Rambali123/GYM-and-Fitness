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
#  SPRINT 2 — MEMBERSHIP PLANS & BILLING (Product Owner: Rajni)
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
    return redirect(url_for('plans'))


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


# ── Run ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)