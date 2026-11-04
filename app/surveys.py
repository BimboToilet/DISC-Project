import datetime as dt
import json

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
    finalize_team_survey,
    get_current_user,
    is_member,
    leader_required,
    login_required,
    notify,
    team_member_ids,
)
from .models import (
    db,
    Invite,
    JoinRequest,
    Membership,
    Survey,
    Team,
    TeamSurvey,
    SurveyResponse,
    User,
)
from .scoring import STYLES, build_reports, compute_user_scores, validate_survey_data

surveys_bp = Blueprint("surveys", __name__)


@surveys_bp.route("/surveys")
@login_required
def library():
    user = get_current_user()
    surveys = (
        Survey.query.filter_by(owner_id=user.id)
        .order_by(Survey.created_at.desc())
        .all()
    )
    return render_template("surveys/library.html", surveys=surveys, user=user)


@surveys_bp.route("/surveys/upload", methods=["POST"])
@login_required
def upload():
    user = get_current_user()
    raw = None
    source = "текст"

    file = request.files.get("file")
    if file and file.filename:
        try:
            raw = file.read().decode("utf-8")
            source = f"файл {file.filename}"
        except UnicodeDecodeError:
            flash("Не удалось прочитать файл: ожидается UTF-8.", "error")
            return redirect(url_for("surveys.library"))
    else:
        raw = request.form.get("json_text") or ""

    if not raw.strip():
        flash("Загрузите файл или вставьте JSON опроса в текстовое поле.", "error")
        return redirect(url_for("surveys.library"))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        flash(f"Некорректный JSON ({source}): {e.msg} (строка {e.lineno}).", "error")
        return redirect(url_for("surveys.library"))

    normalized, errors = validate_survey_data(data)
    if errors:
        for e in errors:
            flash(f"Ошибка формата опроса: {e}", "error")
        return redirect(url_for("surveys.library"))

    survey = Survey(
        owner_id=user.id,
        title=normalized["title"],
        description=normalized["description"],
        data=normalized,
    )
    db.session.add(survey)
    db.session.commit()
    flash(
        f"Опрос «{normalized['title']}» загружен в вашу библиотеку "
        f"({len(normalized['questions'])} вопр.).",
        "success",
    )
    return redirect(url_for("surveys.survey_detail", survey_id=survey.id))


@surveys_bp.route("/surveys/<int:survey_id>")
@login_required
def survey_detail(survey_id):
    user = get_current_user()
    survey = db.session.get(Survey, survey_id)
    if survey is None or survey.owner_id != user.id:
        abort(404)
    return render_template("surveys/detail.html", survey=survey, user=user)


@surveys_bp.route("/surveys/<int:survey_id>/delete", methods=["POST"])
@login_required
def delete_survey(survey_id):
    user = get_current_user()
    survey = db.session.get(Survey, survey_id)
    if survey is None or survey.owner_id != user.id:
        abort(404)

    active_assignment = TeamSurvey.query.filter_by(
        survey_id=survey.id, status="active"
    ).first()
    if active_assignment:
        flash(
            "Опрос сейчас назначен на команду и активен — сначала завершите его.",
            "error",
        )
        return redirect(url_for("surveys.survey_detail", survey_id=survey.id))
    db.session.delete(survey)
    db.session.commit()
    flash("Опрос удален из библиотеки.", "success")
    return redirect(url_for("surveys.library"))


def _parse_deadline(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return False


@surveys_bp.route("/teams/<int:team_id>/surveys/assign", methods=["POST"])
@leader_required
def assign_survey(team_id, team):
    user = get_current_user()
    active = TeamSurvey.query.filter_by(team_id=team.id, status="active").first()
    if active:
        flash(
            "На команду уже назначен активный опрос — одновременно активен только один. "
            "Завершите текущий, чтобы назначить новый.",
            "error",
        )
        return redirect(url_for("teams.team_detail", team_id=team.id))

    try:
        survey_id = int(request.form.get("survey_id"))
    except (TypeError, ValueError):
        flash("Выберите опрос из вашей библиотеки.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))

    survey = db.session.get(Survey, survey_id)
    if survey is None or survey.owner_id != user.id:
        flash("Опрос не найден в вашей библиотеке.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))

    deadline = _parse_deadline(request.form.get("deadline"))
    if deadline is False:
        flash("Некорректный формат дедлайна.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))
    if deadline is not None and deadline <= dt.datetime.now():
        flash("Дедлайн должен быть в будущем.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))

    ts = TeamSurvey(
        team_id=team.id,
        survey_id=survey.id,
        created_by=user.id,
        survey_snapshot=survey.data,
        deadline=deadline,
        status="active",
    )
    db.session.add(ts)
    db.session.flush()

    members = team_member_ids(team.id)
    for uid in members:
        if uid == user.id:
            continue
        notify(
            uid,
            "survey_assigned",
            f"Новый DISC-опрос: «{survey.title}»",
            f"Лидер команды «{team.name}» назначил прохождение опроса."
            + (
                f" Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}."
                if deadline
                else " Дедлайн не указан."
            ),
            {"team_survey_id": ts.id, "team_id": team.id, "team_name": team.name},
        )

    dl = f" до {deadline.strftime('%d.%m.%Y %H:%M')}" if deadline else ""
    chat_message(
        team.id,
        f"Лидер назначил DISC-опрос «{survey.title}»{dl}. "
        f"Пройти: на странице команды или из уведомлений.",
        kind="system",
        meta={"team_survey_id": ts.id},
    )
    db.session.commit()
    flash(f"Опрос «{survey.title}» назначен команде.", "success")
    return redirect(url_for("teams.team_detail", team_id=team.id))


@surveys_bp.route("/teams/<int:team_id>/surveys/<int:ts_id>/stop", methods=["POST"])
@leader_required
def stop_survey(team_id, ts_id, team):
    ts = db.session.get(TeamSurvey, ts_id)
    if ts is None or ts.team_id != team.id or ts.status != "active":
        flash("Активный опрос не найден.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))
    finalize_team_survey(ts, reason="manual")
    db.session.commit()
    flash("Опрос прекращен. Отчеты сформированы и разосланы.", "success")
    return redirect(url_for("teams.team_detail", team_id=team.id))


@surveys_bp.route("/surveys/take/<int:ts_id>")
@login_required
def take_survey(ts_id):
    user = get_current_user()
    ts = db.session.get(TeamSurvey, ts_id)
    if ts is None:
        abort(404)
    team = db.session.get(Team, ts.team_id)
    if team is None or not is_member(user.id, team.id):
        abort(403)
    if ts.status != "active":
        flash("Этот опрос уже завершен.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))
    existing = SurveyResponse.query.filter_by(team_survey_id=ts.id, user_id=user.id).first()
    if existing:
        flash("Вы уже прошли этот опрос. Спасибо!", "info")
        return redirect(url_for("teams.team_detail", team_id=team.id))
    return render_template(
        "surveys/take.html",
        ts=ts,
        team=team,
        survey=ts.survey_snapshot,
        user=user,
    )


@surveys_bp.route("/surveys/take/<int:ts_id>", methods=["POST"])
@login_required
def submit_survey(ts_id):
    user = get_current_user()
    ts = db.session.get(TeamSurvey, ts_id)
    if ts is None:
        abort(404)
    team = db.session.get(Team, ts.team_id)
    if team is None or not is_member(user.id, team.id):
        abort(403)
    if ts.status != "active":
        flash("Опрос уже завершен — ответы больше не принимаются.", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))
    existing = SurveyResponse.query.filter_by(team_survey_id=ts.id, user_id=user.id).first()
    if existing:
        flash("Вы уже прошли этот опрос.", "info")
        return redirect(url_for("teams.team_detail", team_id=team.id))

    snapshot = ts.survey_snapshot
    answers = {}
    for q in snapshot.get("questions", []):
        val = request.form.get(f"q_{q['id']}")
        if val is None:
            continue
        try:
            answers[str(q["id"])] = int(val)
        except (TypeError, ValueError):
            continue

    if not answers:
        flash("Ответьте хотя бы на один вопрос.", "error")
        return redirect(url_for("surveys.take_survey", ts_id=ts.id))

    resp = SurveyResponse(team_survey_id=ts.id, user_id=user.id, answers=answers)
    db.session.add(resp)
    db.session.flush()

    members = team_member_ids(team.id)
    responded = {
        r.user_id
        for r in SurveyResponse.query.filter_by(team_survey_id=ts.id).all()
    }
    all_done = members and members <= responded
    if all_done:
        finalize_team_survey(ts, reason="completed")
        db.session.commit()
        flash(
            "Спасибо! Опрос пройден. Все участники ответили — опрос завершен, "
            "отчеты сформированы.",
            "success",
        )
    else:
        db.session.commit()
        flash("Спасибо! Ваши ответы сохранены.", "success")
    return redirect(url_for("teams.team_detail", team_id=team.id))


def _load_finished(ts_id):
    user = get_current_user()
    ts = db.session.get(TeamSurvey, ts_id)
    if ts is None:
        abort(404)
    team = db.session.get(Team, ts.team_id)
    if team is None or not is_member(user.id, team.id):
        abort(403)
    if ts.status != "finished" or not ts.results:
        abort(404)
    return user, ts, team


@surveys_bp.route("/reports/<int:ts_id>/personal")
@login_required
def report_personal(ts_id):
    user, ts, team = _load_finished(ts_id)
    results = ts.results
    personal = (results.get("personal") or {}).get(str(user.id))
    if personal is None:
        flash("Ваш персональный отчет недоступен (вы не проходили этот опрос).", "error")
        return redirect(url_for("teams.team_detail", team_id=team.id))
    snapshot = ts.survey_snapshot or {}
    return render_template(
        "reports/personal.html",
        ts=ts,
        team=team,
        personal=personal,
        snapshot=snapshot,
        styles=STYLES,
        user=user,
        results=results,
    )


@surveys_bp.route("/reports/<int:ts_id>/team")
@login_required
def report_team(ts_id):
    user, ts, team = _load_finished(ts_id)
    return render_template(
        "reports/team.html",
        ts=ts,
        team=team,
        team_report=ts.results.get("team") or {},
        snapshot=ts.survey_snapshot or {},
        styles=STYLES,
        user=user,
    )


@surveys_bp.route("/reports/<int:ts_id>/management")
@login_required
def report_management(ts_id):
    user, ts, team = _load_finished(ts_id)
    if team.leader_id != user.id:
        abort(403)
    return render_template(
        "reports/management.html",
        ts=ts,
        team=team,
        report=ts.results.get("management") or {},
        team_report=ts.results.get("team") or {},
        snapshot=ts.survey_snapshot or {},
        styles=STYLES,
        user=user,
    )
