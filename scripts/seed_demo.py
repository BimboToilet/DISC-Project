import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402
from app.models import Membership, Survey, Team, User, db  # noqa: E402

app = create_app()
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def main():
    with app.app_context():
        demo_users = [
            ("anna", "Анна Соколова"),
            ("boris", "Борис Петров"),
            ("vera", "Вера Кузнецова"),
        ]
        users = {}
        for username, display_name in demo_users:
            u = User.query.filter_by(username=username).first()
            if not u:
                u = User(username=username, display_name=display_name)
                u.set_password("demo123")
                db.session.add(u)
            users[username] = u
        db.session.flush()

        team = Team.query.filter_by(name="Продукт").first()
        if not team:
            team = Team(
                name="Продукт",
                description="Демо-команда продуктовой группы",
                leader_id=users["anna"].id,
            )
            db.session.add(team)
            db.session.flush()
            db.session.add(Membership(team_id=team.id, user_id=users["anna"].id, role="leader"))
            db.session.add(Membership(team_id=team.id, user_id=users["boris"].id, role="member"))

        example = os.path.join(
            os.path.dirname(__file__), "..", "examples", "disc_survey_example.json"
        )
        if os.path.exists(example):
            import json

            with open(example, encoding="utf-8") as f:
                data = json.load(f)
            if not Survey.query.filter_by(owner_id=users["anna"].id, title=data["title"]).first():
                db.session.add(
                    Survey(
                        owner_id=users["anna"].id,
                        title=data["title"],
                        description=data.get("description", ""),
                        data=data,
                    )
                )

        db.session.commit()
        print("Демо-данные готовы:")
        print("  anna / demo123  — лидер команды «Продукт» (опрос в библиотеке)")
        print("  boris / demo123 — участник команды")
        print("  vera / demo123  — без команды (может подать заявку)")


if __name__ == "__main__":
    main()
