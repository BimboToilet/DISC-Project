from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .helpers import get_current_user
from .models import User, db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.before_app_request
def _load_user():
    g.user_id = session.get("user_id")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if get_current_user():
        return redirect(url_for("teams.dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        display_name = (request.form.get("display_name") or "").strip()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""

        errors = []
        if not username or len(username) < 3:
            errors.append("Логин должен быть не короче 3 символов.")
        if not username.replace("_", "").replace(".", "").isalnum():
            errors.append("Логин может содержать только буквы, цифры, «_» и «.».")
        if not display_name:
            errors.append("Укажите имя (оно будет отображаться другим пользователям).")
        if len(password) < 6:
            errors.append("Пароль должен быть не короче 6 символов.")
        if password != password2:
            errors.append("Пароли не совпадают.")
        if not errors and User.query.filter_by(username=username).first():
            errors.append("Пользователь с таким логином уже существует.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "auth/register.html",
                username=username,
                display_name=display_name,
            )

        user = User(username=username, display_name=display_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        flash("Регистрация успешна. Добро пожаловать.", "success")
        return redirect(url_for("teams.dashboard"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("teams.dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("Неверный логин или пароль.", "error")
            return render_template("auth/login.html", username=username)
        session["user_id"] = user.id
        session.permanent = True
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("teams.dashboard"))
    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Вы вышли из системы.", "success")
    return redirect(url_for("auth.login"))
