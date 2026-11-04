import datetime as dt

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from .helpers import (
    add_member,
    chat_message,
    get_current_user,
    login_required,
    notify,
    unread_count,
)
from .models import db, Invite, JoinRequest, Notification, Team, User

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def _mark_handled(notification):
    notification.read = True
    payload = notification.payload or {}
    payload["handled"] = True
    notification.payload = payload


@notifications_bp.route("/unread-count")
@login_required
def unread_count_json():
    user = get_current_user()
    return jsonify({"count": unread_count(user.id)})


@notifications_bp.route("")
@login_required
def list_notifications():
    user = get_current_user()
    items = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(200)
        .all()
    )

    for n in items:
        n.read = True
    db.session.commit()
    return render_template(
        "notifications/list.html",
        items=items,
        user=user,
        unread=0,
    )


@notifications_bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    user = get_current_user()
    n = db.session.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        abort(404)
    n.read = True
    db.session.commit()
    return redirect(request.form.get("next") or url_for("notifications.list_notifications"))


@notifications_bp.route("/<int:notification_id>/action/<string:action>", methods=["POST"])
@login_required
def handle_action(notification_id, action):
    user = get_current_user()
    n = db.session.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        abort(404)
    if (n.payload or {}).get("handled"):
        flash("Это уведомление уже обработано.", "info")
        return redirect(url_for("notifications.list_notifications"))

    payload = n.payload or {}

    if n.type == "team_invite":
        inv = db.session.get(Invite, payload.get("invite_id", -1))
        if inv is None or inv.status != "pending":
            flash("Приглашение уже неактуально.", "error")
            _mark_handled(n)
            db.session.commit()
            return redirect(url_for("notifications.list_notifications"))
        team = db.session.get(Team, inv.team_id)
        if team is None:
            flash("Команда не найдена.", "error")
            _mark_handled(n)
            db.session.commit()
            return redirect(url_for("notifications.list_notifications"))

        if action == "accept":
            inv.status = "accepted"
            inv.handled_at = dt.datetime.now()
            added = add_member(team.id, user.id)
            if added:
                chat_message(
                    team.id,
                    f"{user.display_name} принял(а) приглашение и присоединился(лась) к команде.",
                    kind="system",
                )
                notify(
                    team.leader_id,
                    "info",
                    f"{user.display_name} принял(а) приглашение",
                    f"Пользователь {user.display_name} присоединился(лась) к команде «{team.name}».",
                    {"team_id": team.id},
                )
            _mark_handled(n)
            db.session.commit()
            flash(f"Вы присоединились к команде «{team.name}».", "success")
            return redirect(url_for("teams.team_detail", team_id=team.id))

        elif action == "decline":
            inv.status = "declined"
            inv.handled_at = dt.datetime.now()
            notify(
                team.leader_id,
                "info",
                f"{user.display_name} отклонил(а) приглашение",
                f"Пользователь {user.display_name} отклонил(а) приглашение в команду «{team.name}».",
                {},
            )
            _mark_handled(n)
            db.session.commit()
            flash("Приглашение отклонено.", "success")
            return redirect(url_for("notifications.list_notifications"))

    elif n.type == "join_request":
        jr = db.session.get(JoinRequest, payload.get("request_id", -1))
        if jr is None or jr.status != "pending":
            flash("Заявка уже обработана.", "info")
            _mark_handled(n)
            db.session.commit()
            return redirect(url_for("notifications.list_notifications"))
        team = db.session.get(Team, jr.team_id)
        if team is None or team.leader_id != user.id:
            flash("Заявка не найдена.", "error")
            _mark_handled(n)
            db.session.commit()
            return redirect(url_for("notifications.list_notifications"))

        if action == "accept":
            jr.status = "accepted"
            jr.handled_at = dt.datetime.now()
            added = add_member(team.id, jr.user_id)
            if added:
                applicant = db.session.get(User, jr.user_id)
                chat_message(
                    team.id,
                    f"{applicant.display_name} принят(а) в команду.",
                    kind="system",
                )
                notify(
                    jr.user_id,
                    "info",
                    f"Заявка принята: команда «{team.name}»",
                    f"Ваша заявка на вступление в команду «{team.name}» принята. Добро пожаловать!",
                    {"team_id": team.id},
                )
            _mark_handled(n)
            db.session.commit()
            flash("Заявка принята.", "success")
            return redirect(url_for("teams.team_detail", team_id=team.id))

        elif action == "decline":
            jr.status = "declined"
            jr.handled_at = dt.datetime.now()
            notify(
                jr.user_id,
                "info",
                f"Заявка отклонена: команда «{team.name}»",
                f"Ваша заявка на вступление в команду «{team.name}» отклонена.",
                {},
            )
            _mark_handled(n)
            db.session.commit()
            flash("Заявка отклонена.", "success")
            return redirect(url_for("notifications.list_notifications"))

    flash("Неизвестное действие.", "error")
    return redirect(url_for("notifications.list_notifications"))
