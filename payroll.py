import os
import mysql.connector
from dataclasses import dataclass
from functools import wraps
from datetime import datetime


DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Jazz@123",
    "database": "payroll_db"
}


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


class PayrollError(Exception):
    pass


def audit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        print(f"[AUDIT] {func.__name__} completed")
        return result
    return wrapper


@dataclass
class Employee:
    employee_id: str
    name: str
    rate: float

    def gross_pay(self, hours):
        return self.rate * hours

    def __str__(self):
        return f"{self.employee_id:<8} {self.name[:25]:<25} Rate: {self.rate:.2f}"


class FullTimeEmployee(Employee):

    def gross_pay(self, hours):
        regular = min(hours, 8) * self.rate
        overtime = max(0, hours - 8) * self.rate * 1.5
        return regular + overtime


class PartTimeEmployee(Employee):

    def gross_pay(self, hours):
        return hours * self.rate


@dataclass
class Attendance:
    employee_id: str
    day: str
    attendance_time: str
    hours: float


class EmployeeIterator:

    def __init__(self, employees):
        self.items = list(employees)
        self.index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= len(self.items):
            raise StopIteration

        item = self.items[self.index]
        self.index += 1
        return item


class Payroll:

    def __init__(self):
        self.employees = {}
        self.attendance = []
        self.payroll_records = []
        self.load()

    def load(self):
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT employee_id, name, rate, employee_type
                FROM employees
            """)

            rows = cursor.fetchall()

            for row in rows:
                if row["employee_type"] == "full":
                    employee = FullTimeEmployee(
                        row["employee_id"],
                        row["name"],
                        float(row["rate"])
                    )
                else:
                    employee = PartTimeEmployee(
                        row["employee_id"],
                        row["name"],
                        float(row["rate"])
                    )

                self.employees[row["employee_id"]] = employee

            cursor.execute("""
                SELECT employee_id, day, attendance_time, hours
                FROM attendance
                ORDER BY day
            """)

            rows = cursor.fetchall()

            for row in rows:
                self.attendance.append(
                    Attendance(
                        row["employee_id"],
                        str(row["day"]),
                        str(row["attendance_time"])
                        if row["attendance_time"] else "",
                        float(row["hours"])
                    )
                )

            cursor.execute("""
                SELECT *
                FROM payroll
            """)

            self.payroll_records = cursor.fetchall()

        finally:
            cursor.close()
            connection.close()

    @audit
    def add_employee(self, employee):

        if employee.employee_id in self.employees:
            raise PayrollError("Employee ID already exists")

        if not employee.employee_id:
            raise PayrollError("Employee ID cannot be empty")

        if not employee.name:
            raise PayrollError("Name cannot be empty")

        if employee.rate <= 0:
            raise PayrollError("Rate must be positive")

        employee_type = (
            "full"
            if isinstance(employee, FullTimeEmployee)
            else "part"
        )

        connection = get_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO employees
                (employee_id, name, rate, employee_type)
                VALUES (%s, %s, %s, %s)
            """, (
                employee.employee_id,
                employee.name,
                employee.rate,
                employee_type
            ))

            connection.commit()
            self.employees[employee.employee_id] = employee

        except mysql.connector.Error as error:
            connection.rollback()
            raise PayrollError(f"MySQL Error: {error}")

        finally:
            cursor.close()
            connection.close()

    @audit
    def record_attendance(self, employee_id, hours):

        if employee_id not in self.employees:
            raise PayrollError("Employee not found")

        if not 0 <= hours <= 24:
            raise PayrollError("Hours must be between 0 and 24")

        now = datetime.now()
        day = now.strftime("%Y-%m-%d")
        attendance_time = now.strftime("%H:%M:%S")

        connection = get_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                SELECT id
                FROM attendance
                WHERE employee_id = %s
                AND day = %s
            """, (employee_id, day))

            existing = cursor.fetchone()

            if existing:
                cursor.execute("""
                    UPDATE attendance
                    SET hours = %s,
                        attendance_time = %s
                    WHERE employee_id = %s
                    AND day = %s
                """, (
                    hours,
                    attendance_time,
                    employee_id,
                    day
                ))
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

            connection.commit()

            found = False

            for item in self.attendance:
                if (
                    item.employee_id == employee_id
                    and item.day == day
                ):
                    item.hours = hours
                    item.attendance_time = attendance_time
                    found = True
                    break

            if not found:
                self.attendance.append(
                    Attendance(
                        employee_id,
                        day,
                        attendance_time,
                        hours
                    )
                )

            print(f"Date: {day}")
            print(f"Day: {now.strftime('%A')}")
            print(f"Time: {attendance_time}")

        except mysql.connector.Error as error:
            connection.rollback()
            raise PayrollError(f"MySQL Error: {error}")

        finally:
            cursor.close()
            connection.close()

    @audit
    def update_employee(self, employee_id, name=None, rate=None):

        if employee_id not in self.employees:
            raise PayrollError("Employee not found")

        employee = self.employees[employee_id]

        if name:
            employee.name = name

        if rate is not None:
            if rate <= 0:
                raise PayrollError("Rate must be positive")
            employee.rate = rate

        connection = get_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                UPDATE employees
                SET name = %s,
                    rate = %s
                WHERE employee_id = %s
            """, (
                employee.name,
                employee.rate,
                employee_id
            ))

            connection.commit()

        except mysql.connector.Error as error:
            connection.rollback()
            raise PayrollError(f"MySQL Error: {error}")

        finally:
            cursor.close()
            connection.close()

    @audit
    def remove_employee(self, employee_id):

        if employee_id not in self.employees:
            raise PayrollError("Employee not found")

        connection = get_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                DELETE FROM employees
                WHERE employee_id = %s
            """, (employee_id,))

            connection.commit()

            del self.employees[employee_id]

            self.attendance = [
                item
                for item in self.attendance
                if item.employee_id != employee_id
            ]

        except mysql.connector.Error as error:
            connection.rollback()
            raise PayrollError(f"MySQL Error: {error}")

        finally:
            cursor.close()
            connection.close()

    def search(self, text):

        text = text.lower().strip()

        return [
            employee
            for employee in self.employees.values()
            if text in employee.name.lower()
            or text in employee.employee_id.lower()
        ]

    def calculate(self, employee_id, bonus=0.0, month=None):

        if employee_id not in self.employees:
            raise PayrollError("Employee not found")

        if bonus < 0:
            raise PayrollError("Bonus cannot be negative")

        employee = self.employees[employee_id]

        if month is None:
            month = datetime.now().strftime("%Y-%m")

        employee_attendance = [
            item
            for item in self.attendance
            if item.employee_id == employee_id
            and item.day.startswith(month)
        ]

        regular_hours = 0
        overtime_hours = 0

        for item in employee_attendance:

            if isinstance(employee, FullTimeEmployee):
                regular_hours += min(item.hours, 8)
                overtime_hours += max(0, item.hours - 8)

            else:
                regular_hours += item.hours

        regular_pay = regular_hours * employee.rate

        if isinstance(employee, FullTimeEmployee):
            overtime_pay = overtime_hours * employee.rate * 1.5
        else:
            overtime_pay = 0

        return {
            "employee_id": employee_id,
            "name": employee.name,
            "month": month,
            "regular_hours": regular_hours,
            "overtime_hours": overtime_hours,
            "regular_pay": regular_pay,
            "overtime_pay": overtime_pay,
            "bonus": bonus
        }

    def payslips(self, month=None):

        if month is None:
            month = datetime.now().strftime("%Y-%m")

        result = []

        for employee in sorted(
            self.employees.values(),
            key=lambda e: e.name.lower()
        ):
            pay = self.calculate(
                employee.employee_id,
                month=month
            )

            result.append(
                (employee, pay)
            )

        return result

    def present_ids(self, day=None):

        if day is None:
            day = datetime.now().strftime("%Y-%m-%d")

        return {
            item.employee_id
            for item in self.attendance
            if item.day == day
            and item.hours > 0
        }

    def absent_ids(self, day):

        present = {
            item.employee_id
            for item in self.attendance
            if item.day == day
            and item.hours > 0
        }

        return set(self.employees) - present

    def overtime_employees(self, month=None):

        if month is None:
            month = datetime.now().strftime("%Y-%m")

        result = []

        for employee in self.employees.values():

            pay = self.calculate(
                employee.employee_id,
                month=month
            )

            if pay["overtime_hours"] > 0:
                result.append(
                    (employee, pay)
                )

        return result

    def save_payroll_record(self, pay, payroll_date):

        connection = get_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO payroll
                (
                    employee_id,
                    regular_hours,
                    overtime_hours,
                    regular_pay,
                    overtime_pay,
                    bonus,
                    payroll_date
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                pay["employee_id"],
                pay["regular_hours"],
                pay["overtime_hours"],
                pay["regular_pay"],
                pay["overtime_pay"],
                pay["bonus"],
                payroll_date
            ))

            connection.commit()

            self.payroll_records.append(
                dict(
                    pay,
                    payroll_date=payroll_date
                )
            )

        except mysql.connector.Error as error:
            connection.rollback()
            raise PayrollError(f"MySQL Error: {error}")

        finally:
            cursor.close()
            connection.close()

    def monthly_summary(self, month):

        summary = []

        for employee in sorted(
        
            self.employees.values(),
            key=lambda e: e.name.lower()
        ):

            pay = self.calculate(
                employee.employee_id,
                month=month
            )

            summary.append(pay)

        return summary


def show_payslip(employee, pay, attendance):
    
    

    print("\n========== INDIVIDUAL PAYSLIP ==========")

    print(f"Employee ID    : {employee.employee_id}")
    print(f"Name           : {employee.name}")
    print(f"Payroll Month  : {pay['month']}")

    print("\nAttendance Details")
    print("-" * 45)

    found = False

    for item in attendance:

        if (
            item.employee_id == employee.employee_id
            and item.day.startswith(pay["month"])
        ):

            date_object = datetime.strptime(
                item.day,
                "%Y-%m-%d"
            )

            print(f"Date           : {item.day}")
            print(f"Day            : {date_object.strftime('%A')}")
            print(f"Time           : {item.attendance_time}")
            print(f"Hours Worked   : {item.hours:.2f}")
            print("-" * 45)

            found = True

    if not found:
        print("No attendance recorded for this month.")
        print("-" * 45)

    print(f"Regular Hours  : {pay['regular_hours']:.2f}")
    print(f"Overtime Hours : {pay['overtime_hours']:.2f}")
    print(f"Regular Pay    : {pay['regular_pay']:.2f}")
    print(f"Overtime Pay   : {pay['overtime_pay']:.2f}")
    print(f"Bonus          : {pay['bonus']:.2f}")

    print("========================================")


def main():

    try:
        payroll = Payroll()

    except mysql.connector.Error as error:

        print("\nMySQL connection failed!")
        print("Error:", error)
        print("\nCheck:")
        print("1. MySQL Server is running")
        print("2. Username is correct")
        print("3. Password is correct")
        print("4. Database payroll_db exists")

        return

    while True:

        print("""
========== EMPLOYEE ATTENDANCE & PAYROLL ==========

1. Add employee
2. Record attendance
3. View individual payslip
4. View all payslips
5. List employees
6. Search employee
7. Update employee
8. Remove employee
9. View present employees
10. View absent employees
11. View overtime employees
12. Monthly payroll summary
13. Exit

====================================================
""")

        choice = input("Choose: ").strip()

        try:

            if choice == "1":

                employee_type = input(
                    "Full-time? (y/n): "
                ).strip().lower()

                if employee_type == "y":
                    cls = FullTimeEmployee
                elif employee_type == "n":
                    cls = PartTimeEmployee
                else:
                    raise PayrollError("Please enter only y or n")

                employee_id = input("ID: ").strip()
                name = input("Name: ").strip()
                rate = float(input("Hourly rate: "))

                employee = cls(
                    employee_id,
                    name,
                    rate
                )

                payroll.add_employee(employee)

                print("Employee added successfully.")

            elif choice == "2":

                employee_id = input(
                    "Employee ID: "
                ).strip()

                hours = float(
                    input("Hours worked (0-24): ")
                )

                payroll.record_attendance(
                    employee_id,
                    hours
                )

                if hours > 0:
                    print("Attendance recorded: PRESENT")
                else:
                    print("Attendance recorded: ABSENT")

            elif choice == "3":

                employee_id = input(
                    "Employee ID: "
                ).strip()

                month = input(
                    "Enter month (YYYY-MM): "
                ).strip()

                if not month:
                    month = datetime.now().strftime("%Y-%m")

                bonus_input = input(
                    "Bonus: "
                ).strip()

                bonus = float(
                    bonus_input
                ) if bonus_input else 0.0

                pay = payroll.calculate(
                    employee_id,
                    bonus=bonus,
                    month=month
                )

                show_payslip(
                    payroll.employees[employee_id],
                    pay,
                    payroll.attendance
                )
                
                while True:
                    save = input(
                        "Save payroll record? (y/n): "
                    ).strip().lower()

                    if save in ("y", "n"):
                        break

                    print("Please enter only 'y' or 'n'.")

                if save == "y":
                    payroll_date = datetime.now().strftime(
                        "%Y-%m-%d"
                    )

                    payroll.save_payroll_record(
                        pay,
                        payroll_date
                    )

                    print("Payroll record saved to MySQL.")

            elif choice == "4":

                month = input(
                    "Enter month (YYYY-MM): "
                ).strip()

                if not month:
                    month = datetime.now().strftime("%Y-%m")

                payslips = payroll.payslips(month)

                print(
                    f"\n===== PAYSLIPS: {month} ====="
                )

                for employee, pay in payslips:

                    print(
                        f"{employee.employee_id} - "
                        f"{employee.name} | "
                        f"Regular Hours: "
                        f"{pay['regular_hours']:.2f} | "
                        f"Overtime Hours: "
                        f"{pay['overtime_hours']:.2f} | "
                        f"Regular Pay: "
                        f"{pay['regular_pay']:.2f} | "
                        f"Overtime Pay: "
                        f"{pay['overtime_pay']:.2f} | "
                        f"Bonus: "
                        f"{pay['bonus']:.2f}"
                    )

            elif choice == "5":

                print("\n===== EMPLOYEES =====")

                for employee in EmployeeIterator(
                    payroll.employees.values()
                ):
                    print(employee)

            elif choice == "6":

                text = input(
                    "Search by ID or name: "
                )

                results = payroll.search(text)

                if results:

                    for employee in results:
                        print(employee)

                else:
                    print("No employee found.")

            elif choice == "7":

                employee_id = input(
                    "Employee ID: "
                ).strip()

                name = input(
                    "New name (blank keeps old): "
                ).strip()

                rate = input(
                    "New rate (blank keeps old): "
                ).strip()

                payroll.update_employee(
                    employee_id,
                    name if name else None,
                    float(rate) if rate else None
                )

                print(
                    "Employee updated successfully."
                )

            elif choice == "8":

                employee_id = input(
                    "Employee ID: "
                ).strip()

                payroll.remove_employee(
                    employee_id
                )

                print(
                    "Employee removed successfully."
                )

            elif choice == "9":

                day = input(
                    "Enter date (YYYY-MM-DD), blank for today: "
                ).strip()

                if not day:
                    day = datetime.now().strftime(
                        "%Y-%m-%d"
                    )

                present = payroll.present_ids(day)

                print(
                    f"\n===== PRESENT EMPLOYEES ({day}) ====="
                )

                for employee_id in sorted(present):

                    print(
                        f"{employee_id} - "
                        f"{payroll.employees[employee_id].name}"
                    )

                if not present:
                    print(
                        "No present employees found."
                    )

            elif choice == "10":

                day = input(
                    "Enter date (YYYY-MM-DD): "
                ).strip()

                absent = payroll.absent_ids(day)

                print(
                    f"\n===== ABSENT EMPLOYEES ({day}) ====="
                )

                for employee_id in sorted(absent):

                    print(
                        f"{employee_id} - "
                        f"{payroll.employees[employee_id].name}"
                    )

                if not absent:
                    print(
                        "No absent employees found."
                    )

            elif choice == "11":

                month = input(
                    "Enter month (YYYY-MM): "
                ).strip()

                if not month:
                    month = datetime.now().strftime(
                        "%Y-%m"
                    )

                overtime = payroll.overtime_employees(
                    month
                )

                print(
                    f"\n===== OVERTIME EMPLOYEES ({month}) ====="
                )

                for employee, pay in overtime:

                    print(
                        f"{employee.employee_id} - "
                        f"{employee.name} | "
                        f"Overtime: "
                        f"{pay['overtime_hours']:.2f} hours | "
                        f"Overtime Pay: "
                        f"{pay['overtime_pay']:.2f}"
                    )

                if not overtime:
                    print(
                        "No overtime employees found."
                    )

            elif choice == "12":

                month = input(
                    "Enter month (YYYY-MM): "
                ).strip()

                summary = payroll.monthly_summary(
                    month
                )

                print(
                    f"\n===== PAYROLL SUMMARY: {month} ====="
                )

                for pay in summary:

                    total_hours = (
                        pay["regular_hours"]
                        + pay["overtime_hours"]
                    )

                    print(
                        f"{pay['employee_id']} - "
                        f"{pay['name']} | "
                        f"Hours: {total_hours:.2f} | "
                        f"Regular: "
                        f"{pay['regular_hours']:.2f} | "
                        f"Overtime: "
                        f"{pay['overtime_hours']:.2f} | "
                        f"Regular Pay: "
                        f"{pay['regular_pay']:.2f} | "
                        f"Overtime Pay: "
                        f"{pay['overtime_pay']:.2f}"
                    )

            elif choice == "13":

                print(
                    "Thank you for using "
                    "Employee Attendance & Payroll System."
                )

                break

            else:

                print("Invalid option.")

        except (
            ValueError,
            PayrollError,
            mysql.connector.Error
        ) as error:

            print(f"Error: {error}")


if __name__ == "__main__":
    main()