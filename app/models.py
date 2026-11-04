from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, default="")
    leader_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    leader = db.relationship("User", foreign_keys=[leader_id])


class Membership(db.Model):
    __tablename__ = "memberships"
    __table_args__ = (db.UniqueConstraint("user_id", "team_id", name="uq_membership"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    role = db.Column(db.String(16), default="member", nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship("User")


class JoinRequest(db.Model):
    __tablename__ = "join_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    message = db.Column(db.Text, default="")
    status = db.Column(db.String(16), default="pending", index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    handled_at = db.Column(db.DateTime)

    user = db.relationship("User")


class Invite(db.Model):
    __tablename__ = "invites"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    inviter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    invitee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(16), default="pending", index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    handled_at = db.Column(db.DateTime)

    invitee = db.relationship("User", foreign_keys=[invitee_id])
    inviter = db.relationship("User", foreign_keys=[inviter_id])


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    type = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, default="")
    payload = db.Column(db.JSON, default=dict)
    read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    kind = db.Column(db.String(16), default="chat", nullable=False)
    body = db.Column(db.Text, nullable=False)
    meta = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    user = db.relationship("User")


class Survey(db.Model):
    __tablename__ = "surveys"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class TeamSurvey(db.Model):
    __tablename__ = "team_surveys"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    survey_id = db.Column(db.Integer, db.ForeignKey("surveys.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    survey_snapshot = db.Column(db.JSON, nullable=False)
    results = db.Column(db.JSON)
    deadline = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(16), default="active", index=True)
    finished_reason = db.Column(db.String(16))
    created_at = db.Column(db.DateTime, default=datetime.now)
    finished_at = db.Column(db.DateTime)

    def active(self) -> bool:
        return self.status == "active"


class SurveyResponse(db.Model):
    __tablename__ = "survey_responses"
    __table_args__ = (
        db.UniqueConstraint("team_survey_id", "user_id", name="uq_response"),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_survey_id = db.Column(
        db.Integer, db.ForeignKey("team_surveys.id"), nullable=False, index=True
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    answers = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship("User")
