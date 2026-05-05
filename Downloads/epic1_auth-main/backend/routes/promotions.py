from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import uuid
import re

from models import db, User, Promotion, Reservation

promotions_bp = Blueprint("promotions", __name__)

IMAGE_REGEX = re.compile(r"^https?://.+\.(jpg|jpeg|png|webp)$", re.IGNORECASE)


def _is_valid_image_url(url):
    if not url or len(url) > 500:
        return False
    return bool(IMAGE_REGEX.match(url))


def _require_restaurant(user):
    return user and user.role == "RESTAURANT"


# US-06 - Publicar promoción
@promotions_bp.route("/promotions", methods=["POST"])
@jwt_required()
def create_promotion():
    data = request.get_json(silent=True) or {}
    user_id = get_jwt_identity()

    user = User.query.get(user_id)
    if not _require_restaurant(user):
        return jsonify({"error": "No autorizado"}), 403

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    price = data.get("price")
    stock = data.get("stock")
    image_url = str(data.get("image_url", "")).strip()
    start_date_raw = str(data.get("start_date", "")).strip()
    end_date_raw = str(data.get("end_date", "")).strip()

    if not all([name, description, price, stock, image_url, start_date_raw, end_date_raw]):
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    try:
        price = float(price)
    except (ValueError, TypeError):
        return jsonify({"error": "Precio inválido"}), 400

    try:
        stock = int(stock)
    except (ValueError, TypeError):
        return jsonify({"error": "Stock inválido"}), 400

    if price <= 0 or stock <= 0:
        return jsonify({"error": "Precio y stock deben ser mayores que 0"}), 400

    if not _is_valid_image_url(image_url):
        return jsonify({"error": "Imagen inválida"}), 400

    try:
        start_date = datetime.fromisoformat(start_date_raw)
        end_date = datetime.fromisoformat(end_date_raw)
    except ValueError:
        return jsonify({"error": "Fechas inválidas"}), 400

    if end_date <= datetime.utcnow():
        return jsonify({"error": "La promoción debe terminar en una fecha futura"}), 400

    duplicate = Promotion.query.filter_by(
        restaurant_id=user.id, name=name, status="ACTIVE"
    ).first()
    if duplicate:
        return jsonify({"error": "Ya existe una promoción activa con ese nombre"}), 409

    promotion = Promotion(
        name=name,
        description=description,
        price=price,
        stock=stock,
        image_url=image_url,
        start_date=start_date,
        end_date=end_date,
        restaurant_id=user.id,
        status="ACTIVE",
    )
    db.session.add(promotion)
    db.session.commit()

    return jsonify({"id": promotion.id, "status": promotion.status}), 201


# US-08 - Reservar promoción (transacción)
@promotions_bp.route("/reservations", methods=["POST"])
@jwt_required()
def create_reservation():
    data = request.get_json(silent=True) or {}
    user_id = get_jwt_identity()
    promotion_id = str(data.get("promotion_id", "")).strip()

    if not promotion_id:
        return jsonify({"error": "promotion_id es obligatorio"}), 400

    try:
        with db.session.begin():
            # Pessimistic lock (SQLite lo ignora, pero en DBs reales funciona)
            promotion = (
                Promotion.query.filter_by(id=promotion_id)
                .with_for_update()
                .first()
            )

            if not promotion or promotion.status != "ACTIVE":
                return jsonify({"error": "Promoción no disponible"}), 404

            if promotion.end_date <= datetime.utcnow() or promotion.stock <= 0:
                return jsonify({"error": "Promoción no disponible"}), 409

            existing = Reservation.query.filter_by(
                user_id=user_id, promotion_id=promotion_id
            ).first()
            if existing:
                return jsonify({"error": "No puedes reservar esta promoción dos veces"}), 409

            promotion.stock -= 1
            coupon_code = uuid.uuid4().hex[:10].upper()

            reservation = Reservation(
                user_id=user_id,
                promotion_id=promotion_id,
                coupon_code=coupon_code,
                status="ACTIVE",
            )
            db.session.add(reservation)

        return jsonify({"coupon_code": coupon_code}), 201

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "No puedes reservar esta promoción dos veces"}), 409
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Ocurrió un error al reservar"}), 500
