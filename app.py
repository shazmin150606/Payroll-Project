from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from functools import wraps
from datetime import datetime
from payroll import Payroll, PayrollError

app = Flask(__name__)
app.secret_key = "payroll_system_secret_key"

payroll = Payroll()

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Jazz@123",
    "database": "payroll_db"
}

USERNAME = "admin"
PASSWORD = "admin123"


def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if username == USERNAME and password == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM employees")
    total_employees = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM attendance
        WHERE day = CURDATE()
    """)
    today_attendance = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM attendance
        WHERE hours > 8
    """)
    overtime_count = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM payroll
    """)
    payroll_count = cursor.fetchone()["total"]

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        total_employees=total_employees,
        today_attendance=today_attendance,
        overtime_count=overtime_count,
        payroll_count=payroll_count
    )


# --------------------------------------------------
# EMPLOYEES
# --------------------------------------------------

@app.route("/employees", methods=["GET", "POST"])
@login_required
def employees():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        employee_id = request.form.get("employee_id")
        name = request.form.get("name")
        rate = request.form.get("rate")
        employee_type = request.form.get("employee_type")

        try:

            cursor.execute("""
                INSERT INTO employees
                (employee_id, name, rate, employee_type)
                VALUES (%s, %s, %s, %s)
            """, (
                employee_id,
                name,
                rate,
                employee_type
            ))

            conn.commit()

            flash("Employee added successfully.", "success")

        except mysql.connector.Error as e:

            conn.rollback()
            flash(str(e), "danger")

    cursor.execute("""
        SELECT *
        FROM employees
        ORDER BY employee_id
    """)

    employee_list = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "employees.html",
        employees=employee_list
    )


@app.route("/employees/edit/<employee_id>", methods=["GET", "POST"])
@login_required
def edit_employee(employee_id):

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        name = request.form.get("name")
        rate = request.form.get("rate")
        employee_type = request.form.get("employee_type")

        try:

            cursor.execute("""
                UPDATE employees
                SET name = %s,
                    rate = %s,
                    employee_type = %s
                WHERE employee_id = %s
            """, (
                name,
                rate,
                employee_type,
                employee_id
            ))

            conn.commit()

            flash("Employee updated successfully.", "success")

        except mysql.connector.Error as e:

            conn.rollback()
            flash(str(e), "danger")

        cursor.close()
        conn.close()

        return redirect(url_for("employees"))

    cursor.execute("""
        SELECT *
        FROM employees
        WHERE employee_id = %s
    """, (employee_id,))

    employee = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "edit_employee.html",
        employee=employee
    )


@app.route("/employees/activate/<employee_id>")
@login_required
def activate_employee(employee_id):

    conn = get_db()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            UPDATE employees
            SET status = 'Active'
            WHERE employee_id = %s
        """, (employee_id,))

        conn.commit()

        flash("Employee activated successfully.", "success")

    except mysql.connector.Error as e:

        conn.rollback()
        flash(str(e), "danger")

    cursor.close()
    conn.close()

    return redirect(url_for("employees"))


@app.route("/employees/deactivate/<employee_id>")
@login_required
def deactivate_employee(employee_id):

    conn = get_db()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            UPDATE employees
            SET status = 'Inactive'
            WHERE employee_id = %s
        """, (employee_id,))

        conn.commit()

        flash("Employee deactivated successfully.", "warning")

    except mysql.connector.Error as e:

        conn.rollback()
        flash(str(e), "danger")

    cursor.close()
    conn.close()

    return redirect(url_for("employees"))


# --------------------------------------------------
# ATTENDANCE
# --------------------------------------------------

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        employee_id = request.form.get("employee_id")
        day = request.form.get("day")
        attendance_time = request.form.get("attendance_time")
        hours = request.form.get("hours")

        try:

            cursor.execute("""
                SELECT status
                FROM employees
                WHERE employee_id = %s
            """, (employee_id,))

            employee = cursor.fetchone()

            if not employee or employee[0] != "Active":

                flash(
                    "Attendance cannot be marked for an inactive employee.",
                    "danger"
                )

            else:

                cursor.execute("""
                    INSERT INTO attendance
                    (employee_id, day, attendance_time, hours)
                    VALUES (%s, %s, %s, %s)
                """, (
                    employee_id,
                    day,
                    attendance_time,
                    hours
                ))

                conn.commit()

                flash("Attendance recorded successfully.", "success")

        except mysql.connector.Error as e:

            conn.rollback()
            flash(str(e), "danger")

    cursor.execute("""
        SELECT
            a.id,
            a.employee_id,
            e.name,
            a.day,
            a.attendance_time,
            a.hours
        FROM attendance a
        JOIN employees e
        ON a.employee_id = e.employee_id
        ORDER BY a.day DESC
    """)

    attendance_list = cursor.fetchall()

    cursor.execute("""
        SELECT employee_id, name
        FROM employees
        WHERE status = 'Active'
        ORDER BY name
    """)

    employee_list = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "attendance.html",
        attendance=attendance_list,
        employees=employee_list
    )


# --------------------------------------------------
# INDIVIDUAL PAYSLIP
# --------------------------------------------------

@app.route("/payslip", methods=["GET", "POST"])
@login_required
def payslip():

    payslip_data = None

    month = datetime.now().strftime("%Y-%m")

    if request.method == "POST":

        employee_id = request.form.get("employee_id")

        month = request.form.get("month")

        try:

            pay = payroll.calculate(
                employee_id,
                month=month
            )

            employee = payroll.employees[employee_id]

            payslip_data = {
                "employee_id": pay["employee_id"],
                "name": pay["name"],
                "employee_type": (
                    "Full Time"
                    if employee.__class__.__name__ == "FullTimeEmployee"
                    else "Part Time"
                ),
                "rate": employee.rate,
                "month": pay["month"],
                "regular_hours": pay["regular_hours"],
                "overtime_hours": pay["overtime_hours"],
                "regular_pay": pay["regular_pay"],
                "overtime_pay": pay["overtime_pay"],
                "bonus": pay["bonus"]
            }

        except Exception as error:

            flash(str(error), "danger")

    employees = [
        {
            "employee_id": employee.employee_id,
            "name": employee.name
        }
        for employee in payroll.employees.values()
    ]

    return render_template(
        "payslip.html",
        payslip=payslip_data,
        employees=employees,
        month=month
    )


# --------------------------------------------------
# ALL PAYSLIPS
# --------------------------------------------------

@app.route("/all-payslips", methods=["GET", "POST"])
@login_required
def all_payslips():

    month = request.form.get("month") if request.method == "POST" else request.args.get("month")

    if not month:
        month = datetime.now().strftime("%Y-%m")

        payslips = payroll.payslips(month)

    return render_template(
        "all_payslips.html",
        payslips=payslips,
        month=month
    )


# --------------------------------------------------
# SEARCH
# --------------------------------------------------

@app.route("/search", methods=["GET", "POST"])
@login_required
def search():

    results = []

    if request.method == "POST":

        keyword = request.form.get("keyword")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM employees
            WHERE employee_id LIKE %s
               OR name LIKE %s
        """, (
            "%" + keyword + "%",
            "%" + keyword + "%"
        ))

        results = cursor.fetchall()

        cursor.close()
        conn.close()

    return render_template(
        "search.html",
        results=results
    )


# --------------------------------------------------
# PRESENT / ABSENT
# --------------------------------------------------

@app.route("/present-absent")
@login_required
def present_absent():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            e.employee_id,
            e.name
        FROM employees e
        INNER JOIN attendance a
        ON e.employee_id = a.employee_id
        WHERE a.day = CURDATE()
    """)

    present = cursor.fetchall()

    cursor.execute("""
        SELECT
            employee_id,
            name
        FROM employees
        WHERE employee_id NOT IN
        (
            SELECT employee_id
            FROM attendance
            WHERE day = CURDATE()
        )
    """)

    absent = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "present_absent.html",
        present=present,
        absent=absent
    )


# --------------------------------------------------
# OVERTIME
# --------------------------------------------------

@app.route("/overtime")
@login_required
def overtime():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            a.employee_id,
            e.name,
            a.day,
            a.hours,
            (a.hours - 8) AS overtime_hours
        FROM attendance a
        JOIN employees e
        ON a.employee_id = e.employee_id
        WHERE a.hours > 8
        ORDER BY a.day DESC
    """)

    overtime_list = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "overtime.html",
        overtime=overtime_list
    )


# --------------------------------------------------
# MONTHLY SUMMARY
# --------------------------------------------------

@app.route("/monthly-summary")
@login_required
def monthly_summary():

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            DATE_FORMAT(a.day, '%Y-%m') AS month,
            COUNT(DISTINCT a.employee_id) AS employees,
            SUM(a.hours) AS total_hours,
            SUM(
                CASE
                    WHEN a.hours > 8
                    THEN a.hours - 8
                    ELSE 0
                END
            ) AS overtime_hours
        FROM attendance a
        GROUP BY DATE_FORMAT(a.day, '%Y-%m')
        ORDER BY month DESC
    """)

    summary = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "monthly_summary.html",
        summary=summary
    )


if __name__ == "__main__":
    app.run(debug=True)