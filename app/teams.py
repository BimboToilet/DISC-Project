from datetime import datetime

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
    is_member,
    leader_required,
    login_required,
    notify,
    team_member_ids,
    unread_count,
)
from .models import (
    db,
    Invite,
    JoinRequest,
    Membership,
    Message,
    Team,
    TeamSurvey,
    Survey,
    SurveyResponse,
    User,
)
from .scoring import STYLES

teams_bp = Blueprint("teams", __name__)


def _fmt_dt(value):
    return value.strftime("%d.%m.%Y %H:%M") if value else ""


@teams_bp.route("/")
@login_required
def dashboard():
    user = get_current_user()
    my_memberships = (
        Membership.query.filter_by(user_id=user.id)
        .order_by(Membership.joined_at.desc())
        .all()
    )
    my_teams = []
    for m in my_memberships:
        team = db.session.get(Team, m.team_id)
        if team:
            my_teams.append({"membership": m, "team": team})

    active_surveys = []
    for item in my_teams:
        ts = TeamSurvey.query.filter_by(
            team_id=item["team"].id, status="active"
        ).first()
        if ts:
            responded = SurveyResponse.query.filter_by(team_survey_id=ts.id).count()
            answered_by_me = SurveyResponse.query.filter_by(
                team_survey_id=ts.id, user_id=user.id
            ).first()
            active_surveys.append(
                {
                    "ts": ts,
                    "team": item["team"],
                    "responded": responded,
                    "answered_by_me": answered_by_me is not None,
                }
            )

    from .models import Notification

    recent_notifications = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard.html",
        user=user,
        my_teams=my_teams,
        active_surveys=active_surveys,
        recent_notifications=recent_notifications,
        unread=unread_count(user.id),
    )


@teams_bp.route("/teams")
@login_required
def list_teams():
    user = get_current_user()
    teams = Team.query.order_by(Team.name).all()
    rows = []
    for team in teams:
        members = Membership.query.filter_by(team_id=team.id).count()
        my_membership = Membership.query.filter_by(
            user_id=user.id, team_id=team.id
        ).first()
        my_request = JoinRequest.query.filter_by(
            user_id=user.id, team_id=team.id, status="pending"
        ).first()
        rows.append(
            {
                "team": team,
                "members": members,
                "my_role": my_membership.role if my_membership else None,
                "pending_request": my_request is not None,
            }
        )
    return render_template("teams/list.html", rows=rows, user=user)


@teams_bp.route("/teams/new", methods=["GET", "POST"])
@login_required
def create_team():
    user = get_current_user()
    all_users = (
        User.query.filter(User.id != user.id).order_by(User.display_name).all()
    )
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        if not name:
            flash("Укажите название команды.", "error")
            return render_template("teams/new.html", all_users=all_users)
        if Team.query.filter_by(name=name).first():
            flash("Команда с таким названием уже существует.", "error")
            return render_template(
                "teams/new.html", all_users=all_users, name=name,
                description=description,
            )

        team = Team(name=name, description=description, leader_id=user.id)
        db.session.add(team)
        db.session.flush()
        db.session.add(
            Membership(team_id=team.id, user_id=user.id, role="leader")
        )

        invited = request.form.getlist("invite_user_ids")
        invited_names = []
        for uid in invited:
            try:
                uid = int(uid)
            except (TypeError, ValueError):
                continue
            invitee = db.session.get(User, uid)
            if invitee is None or is_member(invitee.id, team.id):
                continue
            inv = Invite(team_id=team.id, inviter_id=user.id, invitee_id=invitee.id)
            db.session.add(inv)
            db.session.flush()
            notify(
                invitee.id,
                "team_invite",
                f"Приглашение в команду «{team.name}»",
                f"{user.display_name} приглашает вас присоединиться к команде.",
                {"invite_id": inv.id, "team_id": team.id, "team_name": team.name},
            )
            invited_names.append(invitee.display_name)
        chat_message(
            team.id,
            f"Команда «{team.name}» создана. Лидер: {user.display_name}.",
            kind="system",
        )
        db.session.commit()
        flash(
            f"Команда «{name}» создана."
            + (f" Приглашения отправлены: {', '.join(invited_names)}." if invited_names else ""),
            "success",
        )
        return redirect(url_for("teams.team_detail", team_id=team.id))

    return render_template("teams/new.html", all_users=all_users)


@teams_bp.route("/teams/<int:team_id>")
@login_required
def team_detail(team_id):
    user = get_current_user()
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    if not is_member(user.id, team.id):
        abort(403)

    memberships = (
        Membership.query.filter_by(team_id=team.id)
        .order_by(Membership.role.desc(), Membership.joined_at)
        .all()
    )
    members = [{"m": m, "u": m.user} for m in memberships]

    pending_requests = (
        JoinRequest.query.filter_by(team_id=team.id, status="pending")
        .order_by(JoinRequest.created_at)
        .all()
    )
    pending_invites = (
        Invite.query.filter_by(team_id=team.id, status="pending").all()
    )

    active_ts = TeamSurvey.query.filter_by(team_id=team.id, status="active").first()
    active_info = None
    if active_ts:
        total = team_member_ids(team.id)
        responded = SurveyResponse.query.filter_by(team_survey_id=active_ts.id).count()
        answered_by_me = SurveyResponse.query.filter_by(
            team_survey_id=active_ts.id, user_id=user.id
        ).first()
        active_info = {
            "ts": active_ts,
            "responded": responded,
            "total": len(total),
            "answered_by_me": answered_by_me is not None,
            "deadline": _fmt_dt(active_ts.deadline),
        }

    history = (
        TeamSurvey.query.filter_by(team_id=team.id, status="finished")
        .order_by(TeamSurvey.finished_at.desc())
        .all()
    )

    member_ids = team_member_ids(team.id)
    invitable = [
        u
        for u in User.query.order_by(User.display_name).all()
        if u.id not in member_ids
    ]

    my_surveys = (
        Survey.query.filter_by(owner_id=user.id).order_by(Survey.created_at.desc()).all()
    )

    messages = (
        Message.query.filter_by(team_id=team.id)
        .order_by(Message.id.desc())
        .limit(100)
        .all()
    )
    messages.reverse()

    my_role = Membership.query.filter_by(user_id=user.id, team_id=team.id).first().role

    return render_template(
        "teams/detail.html",
        team=team,
        user=user,
        members=members,
        my_role=my_role,
        pending_requests=pending_requests,
        pending_invites=pending_invites,
        active_info=active_info,
        history=history,
        invitable=invitable,
        my_surveys=my_surveys,
        messages=messages,
        fmt_dt=_fmt_dt,
        styles=STYLES,
    )


@teams_bp.route("/teams/<int:team_id>/apply", methods=["POST"])
@login_required
def apply_to_team(team_id):
    user = get_current_user()
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    if is_member(user.id, team.id):
        flash("Вы уже участник этой команды.", "error")
        return redirect(url_for("teams.list_teams"))
    existing = JoinRequest.query.filter_by(
        user_id=user.id, team_id=team.id, status="pending"
    ).first()
    if existing:
        flash("Заявка уже отправлена — ожидает решения лидера.", "error")
        return redirect(url_for("teams.list_teams"))

    message = (request.form.get("message") or "").strip()
    jr = JoinRequest(user_id=user.id, team_id=team.id, message=message)
    db.session.add(jr)
    db.session.flush()
    notify(
        team.leader_id,
        "join_request",
        f"Заявка на вступление в команду «{team.name}»",
        f"{user.display_name} хочет присоединиться к команде."
        + (f" Сообщение: {message}" if message else ""),
        {"request_id": jr.id, "team_id": team.id, "user_id": user.id},
    )
    db.session.commit()
    flash("Заявка отправлена лидеру команды.", "success")
    return redirect(url_for("teams.list_teams"))


@teams_bp.route("/teams/<int:team_id>/cancel-apply", methods=["POST"])
@login_required
def cancel_apply(team_id):
    user = get_current_user()
    jr = JoinRequest.query.filter_by(
        user_id=user.id, team_id=team_id, status="pending"
    ).first()
    if jr:
        jr.status = "declined"
        jr.handled_at = datetime.now()
        jr.message = jr.message + " (заявка отозвана пользователем)"
        db.session.commit()
        flash("Заявка отменена.", "success")
    return redirect(url_for("teams.list_teams"))


@teams_bp.route("/teams/<int:team_id>/leave", methods=["POST"])
@login_required
def leave_team(team_id):
    user = get_current_user()
    team = db.session.get(Team, team_id)
    if team is None:
        abort(404)
    if team.leader_id == user.id:
        flash(
            "Лидер не может покинуть свою команду. При необходимости удалите её функции через администратора.",
            "error",
        )
        return redirect(url_for("teams.team_detail", team_id=team.id))
    m = Membership.query.filter_by(user_id=user.id, team_id=team.id).first()
    if m:
        db.session.delete(m)
        chat_message(team.id, f"{user.display_name} покинул(а) команду.", kind="system")
        db.session.commit()
        flash("Вы вышли из команды.", "success")
    return redirect(url_for("teams.dashboard"))


@teams_bp.route("/teams/<int:team_id>/invite", methods=["POST"])
@leader_required
def invite_users(team_id, team):
    user = get_current_user()
    uids = request.form.getlist("user_ids")
    sent = []
    for uid in uids:
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            continue
        invitee = db.session.get(User, uid)
        if invitee is None or is_member(invitee.id, team.id):
            continue
        inv = Invite(team_id=team.id, inviter_id=user.id, invitee_id=invitee.id)
        db.session.add(inv)
        db.session.flush()
        notify(
            invitee.id,
            "team_invite",
            f"Приглашение в команду «{team.name}»",
            f"{user.display_name} приглашает вас присоединиться к команде.",
            {"invite_id": inv.id, "team_id": team.id, "team_name": team.name},
        )
        sent.append(invitee.display_name)
    db.session.commit()
    if sent:
        flash(f"Приглашения отправлены: {', '.join(sent)}.", "success")
    else:
        flash("Не выбраны пользователи для приглашения.", "error")
    return redirect(url_for("teams.team_detail", team_id=team.id))


@teams_bp.route("/teams/<int:team_id>/requests/<int:request_id>/<string:action>", methods=["POST"])
@leader_required
def handle_request(team_id, request_id, action, team):
    user = get_current_user()
    jr = db.session.get(JoinRequest, request_id)
    if jr is None or jr.team_id != team.id or jr.status != "pending":
        flash("Заявка не найдена или уже обработана.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))

    if action == "accept":
        jr.status = "accepted"
        added = add_member(team.id, jr.user_id)
        applicant = db.session.get(User, jr.user_id)
        if added and applicant:
            chat_message(
                team.id,
                f"{applicant.display_name} присоединился(лась) к команде (заявка принята).",
                kind="system",
            )
            notify(
                jr.user_id,
                "info",
                f"Заявка принята: команда «{team.name}»",
                f"Ваша заявка на вступление в команду «{team.name}» принята. Добро пожаловать!",
                {"team_id": team.id},
            )
        flash("Заявка принята.", "success")
    elif action == "decline":
        jr.status = "declined"
        notify(
            jr.user_id,
            "info",
            f"Заявка отклонена: команда «{team.name}»",
            f"Ваша заявка на вступление в команду «{team.name}» отклонена лидером.",
            {},
        )
        flash("Заявка отклонена.", "success")
    else:
        abort(404)
    jr.handled_at = datetime.now()
    db.session.commit()
    return redirect(url_for("teams.team_detail", team_id=team.id))


@teams_bp.route("/teams/<int:team_id>/members/<int:user_id>/remove", methods=["POST"])
@leader_required
def remove_member(team_id, user_id, team):
    target = db.session.get(User, user_id)
    if target is None or target.id == team.leader_id:
        flash("Нельзя исключить лидера команды.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))
    m = Membership.query.filter_by(user_id=user_id, team_id=team.id).first()
    if m:
        db.session.delete(m)
        chat_message(team.id, f"{target.display_name} исключен(а) из команды.", kind="system")
        notify(
            user_id,
            "info",
            f"Вы исключены из команды «{team.name}»",
            "Лидер команды исключил вас из состава.",
            {},
        )
        db.session.commit()
        flash(f"{target.display_name} исключен(а) из команды.", "success")
    return redirect(url_for("teams.team_detail", team_id=team.id))


def _message_json(m):
    return {
        "id": m.id,
        "kind": m.kind,
        "user": m.user.display_name if m.user else None,
        "user_id": m.user_id,
        "body": m.body,
        "meta": m.meta or {},
        "time": m.created_at.strftime("%d.%m %H:%M") if m.created_at else "",
    }


@teams_bp.route("/teams/<int:team_id>/chat", methods=["POST"])
@login_required
def post_chat(team_id):
    user = get_current_user()
    team = db.session.get(Team, team_id)
    if team is None or not is_member(user.id, team.id):
        abort(403)
    if request.content_type and "application/json" in request.content_type:
        data = request.get_json(silent=True) or {}
        body = (data.get("body") or "").strip()
        is_json = True
    else:
        body = (request.form.get("body") or "").strip()
        is_json = False
    if not body:
        if is_json:
            return jsonify({"ok": False, "error": "Пустое сообщение"}), 400
        flash("Пустое сообщение.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id) + "#chat")
    m = chat_message(team.id, body, user_id=user.id)
    db.session.commit()
    if is_json:
        return jsonify({"ok": True, "message": _message_json(m)})
    return redirect(url_for("teams.team_detail", team_id=team.id) + "#chat")


@teams_bp.route("/teams/<int:team_id>/chat/poll")
@login_required
def poll_chat(team_id):
    user = get_current_user()
    team = db.session.get(Team, team_id)
    if team is None or not is_member(user.id, team.id):
        abort(403)
    try:
        after = int(request.args.get("after", 0))
    except ValueError:
        after = 0
    msgs = (
        Message.query.filter(Message.team_id == team_id, Message.id > after)
        .order_by(Message.id)
        .limit(50)
        .all()
    )
    return jsonify({"ok": True, "messages": [_message_json(m) for m in msgs]})
