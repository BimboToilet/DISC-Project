import datetime as dt
from functools import wraps

from flask import abort, g, redirect, request, url_for

from .models import (
    db,
    Notification,
    Team,
    TeamSurvey,
    User,
)


def get_current_user():
    uid = g.get("user_id")
    if uid is None:
        return None
    if g.get("user") is None:
        g.user = db.session.get(User, uid)
    return g.get("user")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def leader_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return redirect(url_for("auth.login"))
        team = db.session.get(Team, kwargs.get("team_id"))
        if team is None or team.leader_id != user.id:
            abort(403)
        kwargs["team"] = team
        return view(*args, **kwargs)

    return wrapped


def notify(user_id, type_, title, body="", payload=None):
    n = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        payload=payload or {},
    )
    db.session.add(n)
    return n


def unread_count(user_id) -> int:
    return Notification.query.filter_by(user_id=user_id, read=False).count()


def team_member_ids(team_id) -> set:
    from .models import Membership

    rows = db.session.query(Membership.user_id).filter_by(team_id=team_id).all()
    return {r[0] for r in rows}


def is_member(user_id, team_id) -> bool:
    from .models import Membership

    return (
        Membership.query.filter_by(user_id=user_id, team_id=team_id).first() is not None
    )


def add_member(team_id, user_id, role="member"):
    from .models import Membership

    if is_member(user_id, team_id):
        return False
    db.session.add(Membership(team_id=team_id, user_id=user_id, role=role))
    return True


def chat_message(team_id, body, user_id=None, kind="chat", meta=None):
    from .models import Message

    m = Message(team_id=team_id, user_id=user_id, kind=kind, body=body, meta=meta or {})
    db.session.add(m)
    return m


def finalize_team_survey(ts: TeamSurvey, reason: str):
    from .scoring import build_reports

    if ts.status != "active":
        return
    ts.status = "finished"
    ts.finished_reason = reason
    ts.finished_at = dt.datetime.now()
    ts.results = build_reports(ts)
    db.session.add(ts)
    _announce_results(ts)


def _announce_results(ts: TeamSurvey):
    team = db.session.get(Team, ts.team_id)
    if team is None:
        return
    results = ts.results or {}
    base = {
        "team_id": team.id,
        "team_name": team.name,
        "team_survey_id": ts.id,
        "survey_title": (ts.survey_snapshot or {}).get("title", "DISC-опрос"),
    }

    for uid_str, personal in (results.get("personal") or {}).items():
        notify(
            int(uid_str),
            "personal_report",
            f"Ваш персональный DISC-отчет: «{base['survey_title']}»",
            f"Опрос команды «{team.name}» завершен. Ваш персональный отчет готов.",
            dict(base, user_id=int(uid_str)),
        )

    notify(
        team.leader_id,
        "management_report",
        f"Управленческий отчет: «{base['survey_title']}»",
        f"Опрос команды «{team.name}» завершен. Управленческий отчет доступен по ссылке.",
        dict(base),
    )

    team_report = results.get("team") or {}
    n = team_report.get("participants_count", 0)
    avg = team_report.get("avg_percent") or {}
    avg_str = ", ".join(f"{L}: {v}%" for L, v in avg.items()) if avg else "нет данных"
    chat_message(
        team.id,
        f"Командный отчет по опросу «{base['survey_title']}» готов. "
        f"Участников: {n}. Средний профиль: {avg_str}. "
        f"Подробности: на странице команды (История опросов).",
        kind="report",
        meta=dict(base),
    )


def close_expired_surveys():
    now = dt.datetime.now()
    expired = TeamSurvey.query.filter(
        TeamSurvey.status == "active",
        TeamSurvey.deadline.isnot(None),
        TeamSurvey.deadline <= now,
    ).all()
    if not expired:
        return
    for ts in expired:
        finalize_team_survey(ts, reason="deadline")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
