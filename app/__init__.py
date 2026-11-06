import os
import secrets

from flask import Flask, render_template

from .helpers import close_expired_surveys
from .models import db


def create_app() -> Flask:
    app = Flask(__name__)

    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.environ.get("DATA_DIR", os.path.join(base_dir, "data"))
    os.makedirs(data_dir, exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "sqlite:///" + os.path.join(data_dir, "disc.db").replace("\\", "/")
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    key_path = os.path.join(data_dir, "secret_key")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            app.secret_key = f.read()
    else:
        key = secrets.token_hex(32).encode()
        with open(key_path, "wb") as f:
            f.write(key)
        app.secret_key = key

    db.init_app(app)
    with app.app_context():
        db.create_all()

    from .auth import auth_bp
    from .notifications import notifications_bp
    from .surveys import surveys_bp
    from .teams import teams_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(surveys_bp)
    app.register_blueprint(notifications_bp)

    @app.before_request
    def _auto_close_surveys():
        close_expired_surveys()

    @app.context_processor
    def _inject_globals():
        from .helpers import get_current_user, unread_count

        user = get_current_user()
        return {"user": user, "unread": unread_count(user.id) if user else 0}

    @app.errorhandler(404)
    def _not_found(e):
        return render_template("error.html", code=404), 404

    @app.errorhandler(403)
    def _forbidden(e):
        return render_template("error.html", code=403), 403

    return app
