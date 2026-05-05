from flask import Blueprint, request, jsonify
from models import db, User
from flask_jwt_extended import create_access_token
import secrets
import re
from datetime import datetime, timedelta
from flask import current_app

auth_bp = Blueprint("auth", __name__)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ROLE_OPTIONS = {"USER", "RESTAURANT"}


def _is_strong_password(password, min_length):
    if len(password) < min_length:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    return True

# US-01 - Registro
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name     = data.get("name", "").strip()
    age_raw  = str(data.get("age", "")).strip()
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    role_raw = str(data.get("role", "USER")).strip().upper()

    if not name or not email or not password:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    if not EMAIL_REGEX.match(email):
        return jsonify({"error": "Formato de correo inválido"}), 400

    if role_raw not in ROLE_OPTIONS:
        return jsonify({"error": "Rol inválido"}), 400

    age = None
    if age_raw:
        try:
            age = int(age_raw)
        except ValueError:
            return jsonify({"error": "La edad debe ser numérica"}), 400
        if age < 15:
            return jsonify({"error": "Debes tener al menos 15 años"}), 400

    min_length = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
    if not _is_strong_password(password, min_length):
        return jsonify({"error": f"La contraseña debe tener al menos {min_length} caracteres, una mayúscula y un número"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "El correo ya está registrado"}), 409

    user = User(name=name, age=age, email=email, role=role_raw)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "Usuario registrado exitosamente", "user": user.to_dict()}), 201


# US-02 - Login
@auth_bp.route("/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Correo y contraseña son obligatorios"}), 400

    if not EMAIL_REGEX.match(email):
        return jsonify({"error": "Credenciales inválidas"}), 401

    user = User.query.filter_by(email=email).first()

    if user and user.lock_until and user.lock_until > datetime.utcnow():
        return jsonify({"error": "Cuenta temporalmente bloqueada. Intenta más tarde"}), 423

    if not user or not user.check_password(password) or not user.is_active:
        if user:
            max_attempts = current_app.config.get("MAX_LOGIN_ATTEMPTS", 5)
            lock_minutes = current_app.config.get("LOCKOUT_MINUTES", 15)
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= max_attempts:
                user.lock_until = datetime.utcnow() + timedelta(minutes=lock_minutes)
                user.failed_login_attempts = 0
            db.session.commit()
        return jsonify({"error": "Credenciales inválidas"}), 401

    user.failed_login_attempts = 0
    user.lock_until = None
    db.session.commit()

    token = create_access_token(identity=str(user.id))

    return jsonify({"message": "Login exitoso", "token": token, "user": user.to_dict()}), 200


# US-03 - Recuperar contraseña (genera token, simula envío de correo)
@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data  = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()

    if not email:
        return jsonify({"error": "El correo es obligatorio"}), 400

    if not EMAIL_REGEX.match(email):
        return jsonify({"message": "Si el correo existe, recibirás instrucciones"}), 200

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"message": "Si el correo existe, recibirás instrucciones"}), 200

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    expires_minutes = current_app.config.get("RESET_TOKEN_EXPIRES_MINUTES", 30)
    user.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
    db.session.commit()

    # En producción aquí se enviaría el correo real
    print(f"🔗 Link de recuperación: http://localhost:5500/frontend/forgot_password.html?token={token}")

    return jsonify({"message": "Si el correo existe, recibirás instrucciones"}), 200


# Resetear contraseña con token
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data         = request.get_json(silent=True) or {}
    token        = data.get("token", "").strip()
    new_password = data.get("new_password", "").strip()

    if not token or not new_password:
        return jsonify({"error": "Token y nueva contraseña son obligatorios"}), 400

    min_length = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
    if not _is_strong_password(new_password, min_length):
        return jsonify({"error": f"La contraseña debe tener al menos {min_length} caracteres, una mayúscula y un número"}), 400

    user = User.query.filter_by(reset_token=token).first()

    if not user:
        return jsonify({"error": "Token inválido o expirado"}), 400

    if user.reset_token_expires_at and user.reset_token_expires_at < datetime.utcnow():
        user.reset_token = None
        user.reset_token_expires_at = None
        db.session.commit()
        return jsonify({"error": "Token inválido o expirado"}), 400

    user.set_password(new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    db.session.commit()

    return jsonify({"message": "Contraseña actualizada exitosamente"}), 200
