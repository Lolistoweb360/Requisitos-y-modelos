from flask import Flask
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import Config
from models import db
from routes.auth import auth_bp
from routes.promotions import promotions_bp
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
JWTManager(app)
CORS(app)

app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(promotions_bp, url_prefix="/api")


def ensure_users_schema_updates():
    columns_result = db.session.execute(text("PRAGMA table_info(users)"))
    existing = {row[1] for row in columns_result}
    alter_statements = []
    if "age" not in existing:
        alter_statements.append("ALTER TABLE users ADD COLUMN age INTEGER")
    if "reset_token_expires_at" not in existing:
        alter_statements.append("ALTER TABLE users ADD COLUMN reset_token_expires_at DATETIME")
    if "failed_login_attempts" not in existing:
        alter_statements.append("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0")
    if "lock_until" not in existing:
        alter_statements.append("ALTER TABLE users ADD COLUMN lock_until DATETIME")
    if "is_active" not in existing:
        alter_statements.append("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
    if "role" not in existing:
        alter_statements.append("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'USER'")

    for statement in alter_statements:
        db.session.execute(text(statement))

    if alter_statements:
        db.session.commit()

with app.app_context():
    db.create_all()
    ensure_users_schema_updates()
    print("✅ Base de datos lista")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
