from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection

auth = Blueprint("auth", __name__)

# ---------------- REGISTER ----------------
@auth.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]

        password_hash = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name, email, phone, password_hash) VALUES (?, ?, ?, ?)",
                (name, email, phone, password_hash),
            )
            conn.commit()
            flash("✅ Registration successful! Please login.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            flash("⚠️ Email already exists.", "danger")
            return redirect(url_for("auth.register"))
        finally:
            conn.close()

    return render_template("register.html")

# ---------------- LOGIN ----------------
@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash("✅ Logged in successfully!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("❌ Invalid credentials.", "danger")

    return render_template("login.html")

# ---------------- LOGOUT ----------------
@auth.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


