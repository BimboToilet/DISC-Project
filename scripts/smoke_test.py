import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = "http://127.0.0.1:5000"
PASSED, FAILED = [], []


def check(name, cond, extra=""):
    (PASSED if cond else FAILED).append(name)
    print(("PASS" if cond else "FAIL"), name, extra if not cond else "")


class Client:
    def __init__(self):
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def get(self, path):
        try:
            r = self.opener.open(BASE + path)
            return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def post(self, path, data=None, json_body=None):
        if json_body is not None:
            body = json.dumps(json_body).encode()
            req = urllib.request.Request(
                BASE + path, data=body,
                headers={"Content-Type": "application/json"}, method="POST"
            )
        else:
            body = urllib.parse.urlencode(data or {}).encode()
            req = urllib.request.Request(BASE + path, data=body, method="POST")
        try:
            r = self.opener.open(req)
            return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")


def main():
    c = Client()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    nr = urllib.request.build_opener(NoRedirect())
    try:
        nr.open(BASE + "/")
        check("redirect to login", False)
    except urllib.error.HTTPError as e:
        check("redirect to login", e.code == 302 and "login" in e.headers.get("Location", ""))

    users = [("anna", "Анна Соколова"), ("boris", "Борис Петров"), ("vera", "Вера Кузнецова")]
    for u, dn in users:
        rc = Client()
        s, body = rc.post("/auth/register", {"username": u, "display_name": dn, "password": "demo123", "password2": "demo123"})
        ok = "Регистрация успешна" in body
        check(f"register {u}", ok)

    anna = Client(); boris = Client(); vera = Client()
    for client, (u, _) in [(anna, users[0]), (boris, users[1]), (vera, users[2])]:
        client.post("/auth/login", {"username": u, "password": "demo123"})
        s, body = client.get("/")
        check(f"login {u}", "Привет" in body)

    with open("examples/disc_survey_example.json", encoding="utf-8") as f:
        survey = json.load(f)
    s, _ = anna.post("/surveys/upload", {"json_text": json.dumps(survey, ensure_ascii=False)})
    check("upload survey", s == 200)

    s, body = anna.post("/teams/new", {"name": "Продукт", "description": "тест", "invite_user_ids": str(get_user_id(anna, "boris"))})
    check("create team", s == 200)
    team_id = find_team_id(anna)
    check("team created", team_id is not None)

    s, body = boris.get("/notifications")
    check("boris has invite", "Приглашение в команду" in body)
    nid = find_notification_id(body)
    s, _ = boris.post(f"/notifications/{nid}/action/accept")
    check("boris accepts invite", s in (200, 302))
    s, body = boris.get(f"/teams/{team_id}")
    check("boris is member", "Чат команды" in body)

    s, _ = vera.post(f"/teams/{team_id}/apply", {"message": "Хочу в команду"})
    check("vera applies", s in (200, 302))
    s, body = anna.get("/notifications")
    check("anna sees join request", "заяв" in body.lower())
    nid = find_notification_id(body)
    s, _ = anna.post(f"/notifications/{nid}/action/accept")
    check("anna accepts vera", s in (200, 302))
    s, body = vera.get(f"/teams/{team_id}")
    check("vera is member", "Чат команды" in body)

    s, body = boris.post(f"/teams/{team_id}/chat", json_body={"body": "Привет, команда!"})
    check("chat post json", '"ok":true' in body)
    resp = vera.get(f"/teams/{team_id}/chat/poll?after=0")
    try:
        poll_data = json.loads(resp[1])
        chat_ok = any("Привет" in m["body"] for m in poll_data.get("messages", []))
    except (ValueError, KeyError):
        chat_ok = False
    check("chat poll", chat_ok)

    sid = find_survey_id(anna)
    s, _ = anna.post(f"/teams/{team_id}/surveys/assign", {"survey_id": sid, "deadline": ""})
    check("assign survey", s in (200, 302))

    s, body = boris.get("/notifications")
    check("boris notified about survey", "Новый DISC-опрос" in body)

    ts_id = find_ts_id(anna, team_id, active_only=True)
    check("survey assigned", ts_id is not None)
    for client in (boris, vera, anna):
        answers = {f"q_{q['id']}": 0 for q in survey["questions"]}
        s, body = client.post(f"/surveys/take/{ts_id}", answers)
        check("take survey", s in (200, 302) and "flash-error" not in body)

    s, body = anna.get(f"/teams/{team_id}")
    check("history has survey", "История опросов" in body and "все участники прошли" in body)

    s, body = boris.get(f"/reports/{ts_id}/personal")
    check("personal report", "Персональный DISC-отчет" in body)
    s, body = boris.get(f"/reports/{ts_id}/team")
    check("team report", "Командный DISC-отчет" in body)
    s, body = anna.get(f"/reports/{ts_id}/management")
    check("management report", "Управленческий отчет" in body)
    s, _ = boris.get(f"/reports/{ts_id}/management")
    check("management forbidden for member", s in (302, 403, 404))

    s, body = boris.get("/notifications")
    check("boris got personal report notif", "персональный DISC-отчет" in body)
    s, body = anna.get("/notifications")
    check("anna got management report notif", "Управленческий отчет" in body)

    resp = vera.get(f"/teams/{team_id}/chat/poll?after=0")
    try:
        poll_data = json.loads(resp[1])
        chat_report_ok = any(
            m.get("kind") == "report" and "Командный отчет" in m.get("body", "")
            for m in poll_data.get("messages", [])
        )
    except (ValueError, KeyError):
        chat_report_ok = False
    check("team report in chat", chat_report_ok)

    s, _ = anna.post(f"/teams/{team_id}/surveys/assign", {"survey_id": sid, "deadline": ""})

    s, _ = anna.post(f"/teams/{team_id}/surveys/assign", {"survey_id": sid, "deadline": ""})
    ts2 = find_ts_id(anna, team_id, active_only=True)
    if ts2:
        s, body = anna.post(f"/teams/{team_id}/surveys/assign", {"survey_id": sid, "deadline": ""})
        ts3 = find_ts_id(anna, team_id, active_only=True)
        check("only one active survey", ts3 == ts2)

    if ts2:
        s, _ = anna.post(f"/teams/{team_id}/surveys/{ts2}/stop")
        s, body = anna.get(f"/teams/{team_id}")
        check("survey stopped", "прекращен лидером" in body)

    import sqlite3 as _sqlite3
    import time

    future = time.strftime("%Y-%m-%dT%H:%M", time.localtime(time.time() + 70))
    s, _ = anna.post(f"/teams/{team_id}/surveys/assign", {"survey_id": sid, "deadline": future})
    ts3 = find_ts_id(anna, team_id, active_only=True)
    check("assign with deadline", ts3 is not None)

    db_path = os.path.join(
        os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data")),
        "disc.db",
    )
    con = _sqlite3.connect(db_path)
    con.execute("update team_surveys set deadline = ? where id = ?", ("2000-01-01 00:00:00", ts3))
    con.commit()
    con.close()

    s, body = anna.get(f"/teams/{team_id}")
    check("deadline auto-close", "по дедлайну" in body)
    s, body = boris.get(f"/reports/{ts3}/team")
    check("deadline team report", "Командный DISC-отчет" in body)

    print()
    print(f"PASS: {len(PASSED)}  FAIL: {len(FAILED)}")
    if FAILED:
        print("Failed:", FAILED)
        sys.exit(1)




def get_user_id(client, username="boris"):
    """Берем id пользователя прямо из БД (тест запускается на той же машине)."""
    import sqlite3

    path = os.environ.get(
        "DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data")
    )
    con = sqlite3.connect(os.path.join(path, "disc.db"))
    row = con.execute("select id from users where username=?", (username,)).fetchone()
    return row[0] if row else 0


def find_team_id(client):
    s, body = client.get("/teams")
    m = re.search(r'href="/teams/(\d+)"', body)
    return int(m.group(1)) if m else None


def find_notification_id(body):
    m = re.search(r'/notifications/(\d+)/action/', body)
    return int(m.group(1)) if m else None


def find_survey_id(client):
    s, body = client.get("/surveys")
    m = re.search(r'/surveys/(\d+)"', body)
    return int(m.group(1)) if m else None


def find_ts_id(client, team_id, active_only=False):
    s, body = client.get(f"/teams/{team_id}")
    if active_only:
        m = re.search(r'/surveys/take/(\d+)', body)
    else:
        m = re.search(r'/reports/(\d+)/team', body)
    return int(m.group(1)) if m else None


if __name__ == "__main__":
    main()
