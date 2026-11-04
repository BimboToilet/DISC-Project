import datetime as dt

STYLES = {
    "D": {
        "name": "Доминирование",
        "short": "D",
        "description": (
            "Прямолинейность, ориентация на результат и победы, решительность, "
            "готовность к риску и готовность принимать непопулярные решения."
        ),
        "strengths": "Быстрые решения, драйв, фокус на цели, умение брать ответственность.",
        "risks": "Нетерпеливость, излишняя категоричность, недостаток эмпатии.",
        "team_role": "Двигатель команды: разгоняет темп и толкает к результату.",
    },
    "I": {
        "name": "Влияние",
        "short": "I",
        "description": (
            "Открытость, энтузиазм, коммуникабельность, оптимизм, умение убеждать "
            "и вдохновлять окружающих."
        ),
        "strengths": "Коммуникация, генерация идей, налаживание контактов, мотивация других.",
        "risks": "Импульсивность, недостаток системности, оптимизм сверх меры.",
        "team_role": "Связующее звено команды: создает атмосферу и вовлекает людей.",
    },
    "S": {
        "name": "Постоянство",
        "short": "S",
        "description": (
            "Спокойствие, надежность, терпение, стремление к стабильности, "
            "лояльность и поддержка окружающих."
        ),
        "strengths": "Надежность, умение слушать, создание доверительной атмосферы.",
        "risks": "Сопротивление переменам, избегание конфликтов, медленное включение.",
        "team_role": "Стабилизатор команды: сохраняет баланс и поддерживает людей.",
    },
    "C": {
        "name": "Соответствие",
        "short": "C",
        "description": (
            "Аналитичность, аккуратность, внимание к деталям и качеству, "
            "системность, следование стандартам и правилам."
        ),
        "strengths": "Точность, глубина анализа, качество, работа с данными.",
        "risks": "Перфекционизм, излишняя критичность, медлительность решений.",
        "team_role": "Контроль качества команды: следит за точностью и стандартами.",
    },
}


def validate_survey_data(data):
    """Проверяет структуру опроса. Возвращает (normalized, errors)."""
    errors = []
    if not isinstance(data, dict):
        return None, ["Опрос должен быть JSON-объектом."]

    title = (data.get("title") or "").strip()
    if not title:
        errors.append("Не указано поле title (название опроса).")

    scales = data.get("scales")
    if not isinstance(scales, dict) or not scales:
        errors.append(
            "Не указаны scales — шкалы оценивания, например "
            '{"D": "Доминирование", "I": "Влияние", "S": "Постоянство", "C": "Соответствие"}.'
        )
    else:
        bad = [k for k, v in scales.items() if not isinstance(k, str) or not isinstance(v, str)]
        if bad:
            errors.append(f"Некорректные шкалы: {bad}. Ключ и значение должны быть строками.")

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        errors.append("Не указан список questions (вопросы опроса).")
    else:
        for i, q in enumerate(questions, 1):
            if not isinstance(q, dict):
                errors.append(f"Вопрос {i}: должен быть объектом.")
                continue
            if not (q.get("text") or "").strip():
                errors.append(f"Вопрос {i}: не указан текст (text).")
            options = q.get("options")
            if not isinstance(options, list) or len(options) < 1:
                errors.append(f"Вопрос {i}: должен иметь хотя бы один вариант ответа (options).")
                continue
            for j, opt in enumerate(options, 1):
                if not isinstance(opt, dict):
                    errors.append(f"Вопрос {i}, вариант {j}: должен быть объектом.")
                    continue
                if not (opt.get("text") or "").strip():
                    errors.append(f"Вопрос {i}, вариант {j}: не указан текст варианта.")
                scores = opt.get("scores")
                if not isinstance(scores, dict) or not scores:
                    errors.append(
                        f"Вопрос {i}, вариант {j}: не указаны scores — "
                        "баллы по шкалам, например {\"D\": 2}."
                    )
                    continue
                for letter, pts in scores.items():
                    if not isinstance(pts, (int, float)) or isinstance(pts, bool):
                        errors.append(
                            f"Вопрос {i}, вариант {j}: балл шкалы «{letter}» "
                            "должен быть числом."
                        )

    if errors:
        return None, errors

    normalized_questions = []
    for i, q in enumerate(questions, 1):
        qd = dict(q)
        qid = str(qd.get("id") or f"q{i}")
        qd["id"] = qid
        normalized_questions.append(qd)

    return (
        {
            "title": title,
            "description": (data.get("description") or "").strip(),
            "scales": {str(k): str(v) for k, v in scales.items()},
            "questions": normalized_questions,
        },
        [],
    )


def compute_user_scores(survey_snapshot: dict, answers: dict) -> dict:
    """Считает баллы пользователя по ответам answers: {question_id: option_index}."""
    scales = survey_snapshot.get("scales", {})
    raw = {letter: 0.0 for letter in scales}
    answered = 0
    for q in survey_snapshot.get("questions", []):
        qid = str(q.get("id"))
        sel = answers.get(qid)
        if sel is None:
            continue
        try:
            opt = q["options"][int(sel)]
        except (ValueError, IndexError, KeyError):
            continue
        answered += 1
        for letter, pts in (opt.get("scores") or {}).items():
            raw[str(letter)] = raw.get(str(letter), 0.0) + float(pts)

    total = sum(raw.values())
    if total > 0:
        percent = {k: round(v / total * 100, 1) for k, v in raw.items()}
    else:
        percent = {k: 0.0 for k in raw}

    ranked = sorted(raw, key=lambda k: raw[k], reverse=True)
    dominant = ranked[0] if total > 0 and raw[ranked[0]] > 0 else None
    secondary = ranked[1] if dominant and len(ranked) > 1 and raw[ranked[1]] > 0 else None

    return {
        "raw": {k: round(v, 2) for k, v in raw.items()},
        "percent": percent,
        "dominant": dominant,
        "secondary": secondary,
        "answered": answered,
        "total_questions": len(survey_snapshot.get("questions", [])),
    }


def _style_info(letter):
    if letter and letter in STYLES:
        st = STYLES[letter]
        return {"letter": letter, "name": st["name"], "description": st["description"]}
    return None


def build_reports(ts) -> dict:
    from .models import SurveyResponse

    snapshot = ts.survey_snapshot or {}
    scales = snapshot.get("scales", {})

    participants = []
    for r in SurveyResponse.query.filter_by(team_survey_id=ts.id).all():
        participants.append(
            {
                "user_id": r.user_id,
                "display_name": r.user.display_name,
                "username": r.user.username,
                "scores": compute_user_scores(snapshot, r.answers or {}),
                "submitted_at": r.created_at.strftime("%d.%m.%Y %H:%M")
                if r.created_at
                else "",
            }
        )
    participants.sort(key=lambda p: p["display_name"].lower())

    personal = {}
    for p in participants:
        s = p["scores"]
        personal[str(p["user_id"])] = {
            "display_name": p["display_name"],
            "scores": s,
            "style": _style_info(s["dominant"]),
            "secondary_style": _style_info(s["secondary"]),
            "submitted_at": p["submitted_at"],
        }

    n = len(participants)
    letters = list(scales.keys())

    avg_percent = {L: 0.0 for L in letters}
    avg_raw = {L: 0.0 for L in letters}
    if n:
        for p in participants:
            for L in letters:
                avg_percent[L] += p["scores"]["percent"].get(L, 0)
                avg_raw[L] += p["scores"]["raw"].get(L, 0)
        avg_percent = {L: round(v / n, 1) for L, v in avg_percent.items()}
        avg_raw = {L: round(v / n, 2) for L, v in avg_raw.items()}

    dominant_distribution = {L: 0 for L in letters}
    for p in participants:
        d = p["scores"]["dominant"]
        if d in dominant_distribution:
            dominant_distribution[d] += 1

    team_dominant = max(avg_percent, key=avg_percent.get) if n and any(avg_percent.values()) else None

    team = {
        "participants_count": n,
        "avg_percent": avg_percent,
        "avg_raw": avg_raw,
        "dominant_distribution": dominant_distribution,
        "team_dominant": team_dominant,
        "team_dominant_style": _style_info(team_dominant),
        "members": [
            {
                "user_id": p["user_id"],
                "display_name": p["display_name"],
                "percent": p["scores"]["percent"],
                "dominant": p["scores"]["dominant"],
            }
            for p in participants
        ],
    }

    insights = []
    if n == 0:
        insights.append("Ни один участник не прошел опрос — данных для анализа недостаточно.")
    else:
        for L in letters:
            if dominant_distribution.get(L, 0) == 0 and STYLES.get(L):
                resource = STYLES[L]["strengths"].split(".")[0].lower()
                insights.append(
                    f"В команде нет ни одного участника с доминирующим стилем "
                    f"«{STYLES[L]['name']}» ({L}): {resource} — этого ресурса команде может не хватать."
                )
        if dominant_distribution:
            top_letter = max(dominant_distribution, key=dominant_distribution.get)
            if dominant_distribution[top_letter] >= max(2, round(n * 0.6)):
                insights.append(
                    f"Более 60% участников имеют доминирующий стиль «{STYLES.get(top_letter, {}).get('name', top_letter)}» "
                    f"({top_letter}) — команда однородна: сильна в этом качестве, но уязвима в противоположном."
                )
        if avg_percent and max(avg_percent.values()) >= 40:
            strongest = max(avg_percent, key=avg_percent.get)
            insights.append(
                f"Профиль команды сильно смещен в сторону «{STYLES.get(strongest, {}).get('name', strongest)}» "
                f"({strongest}: {max(avg_percent.values())}% в среднем) — стоит сбалансировать состав или распределение ролей."
            )
        spread = {}
        for L in letters:
            vals = [p["scores"]["percent"].get(L, 0) for p in participants]
            if vals:
                spread[L] = round(max(vals) - min(vals), 1)
        wide = [L for L, v in spread.items() if v >= 40]
        if wide:
            names = ", ".join(f"«{STYLES.get(L, {}).get('name', L)}»" for L in wide)
            insights.append(
                f"Значительный разброс внутри команды по шкалам: {names} "
                "(разница между участниками более 40 п.п.) — вероятны подгруппы с разными "
                "предпочтительными способами работы."
            )

    management = {
        "participants_count": n,
        "avg_percent": avg_percent,
        "team_dominant": team_dominant,
        "members": [
            {
                "display_name": p["display_name"],
                "raw": p["scores"]["raw"],
                "percent": p["scores"]["percent"],
                "dominant": p["scores"]["dominant"],
                "secondary": p["scores"]["secondary"],
                "submitted_at": p["submitted_at"],
                "vs_avg": {
                    L: round(p["scores"]["percent"].get(L, 0) - avg_percent.get(L, 0), 1)
                    for L in letters
                },
            }
            for p in participants
        ],
        "insights": insights,
        "non_participants": [],
    }

    results = {
        "personal": personal,
        "team": team,
        "management": management,
        "generated_at": dt.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "finished_reason": ts.finished_reason,
    }
    return attach_non_participants(ts, results)


def attach_non_participants(ts, results):
    from .helpers import team_member_ids
    from .models import User

    responded = {int(k) for k in (results.get("personal") or {}).keys()}
    missing = []
    for uid in team_member_ids(ts.team_id):
        if uid not in responded:
            u = User.query.get(uid)
            if u:
                missing.append(u.display_name)
    if results.get("management") is not None:
        results["management"]["non_participants"] = sorted(missing, key=str.lower)
    return results
