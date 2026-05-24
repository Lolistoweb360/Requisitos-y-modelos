from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import uuid
import re

from models import db, User, Promotion, Reservation

promotions_bp = Blueprint("promotions", __name__)

IMAGE_REGEX = re.compile(r"^https?://.+\.(jpg|jpeg|png|webp)$", re.IGNORECASE)
COUPON_CODE_LENGTH = 12


def _is_valid_image_url(url):
    if not url or len(url) > 500:
        return False
    return bool(IMAGE_REGEX.match(url))


def _require_restaurant(user):
    return user and user.role == "RESTAURANT"


def _promotion_to_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "price": float(p.price),
        "stock": p.stock,
        "image_url": p.image_url or "",
        "valid_until": p.end_date.isoformat() if p.end_date else None,
        "status": p.status,
        "restaurant_id": p.restaurant_id,
        "user_id": p.restaurant_id,
        "created_at": p.created_at.isoformat(),
        "lat": getattr(p, "lat", None),
        "lng": getattr(p, "lng", None),
    }


def _reservation_to_dict(r, promotion=None):
    d = {
        "id": r.id,
        "coupon_code": r.coupon_code,
        "status": r.status,
        "user_id": r.user_id,
        "promotion_id": r.promotion_id,
        "created_at": r.created_at.isoformat(),
    }
    if promotion:
        d["promotion"] = {
            "id": promotion.id,
            "name": promotion.name,
            "valid_until": promotion.end_date.isoformat() if promotion.end_date else None,
            "image_url": promotion.image_url or "",
        }
    return d


def _do_reserve(user_id, promotion_id):
    try:
        promotion = (
            Promotion.query.filter_by(id=promotion_id)
            .with_for_update()
            .first()
        )

        if not promotion:
            return jsonify({"error": "Promoción no encontrada"}), 404

        if promotion.end_date and promotion.end_date <= datetime.utcnow():
            promotion.status = "INACTIVE"
            db.session.commit()
            return jsonify({"error": "Promoción expirada"}), 400

        if promotion.status != "ACTIVE" or promotion.stock <= 0:
            return jsonify({"error": "Promoción no disponible (agotada o inactiva)"}), 400

        existing = Reservation.query.filter_by(
            user_id=user_id, promotion_id=promotion_id
        ).first()
        if existing:
            return jsonify({"error": "Ya reservaste esta promoción"}), 409

        promotion.stock -= 1
        if promotion.stock == 0:
            promotion.status = "SOLD_OUT"

        coupon_code = uuid.uuid4().hex[:COUPON_CODE_LENGTH].upper()

        reservation = Reservation(
            user_id=user_id,
            promotion_id=promotion_id,
            coupon_code=coupon_code,
            status="ACTIVE",
        )
        db.session.add(reservation)
        db.session.commit()

        return jsonify({
            "id": reservation.id,
            "coupon_code": coupon_code,
            "status": reservation.status,
            "user_id": reservation.user_id,
            "promotion_id": reservation.promotion_id,
            "created_at": reservation.created_at.isoformat(),
        }), 201

    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ya reservaste esta promoción"}), 409
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Ocurrió un error al reservar"}), 500


# GET /api/promotions/my-reservations  (must be registered before /<id>/reserve)
@promotions_bp.route("/promotions/my-reservations", methods=["GET"])
@jwt_required()
def my_reservations():
    user_id = get_jwt_identity()
    reservations = (
        Reservation.query
        .filter_by(user_id=user_id)
        .order_by(Reservation.created_at.desc())
        .all()
    )
    result = []
    for r in reservations:
        promo = Promotion.query.get(r.promotion_id)
        result.append(_reservation_to_dict(r, promo))
    return jsonify(result), 200


# GET /api/promotions - listar promociones activas
@promotions_bp.route("/promotions", methods=["GET"])
@jwt_required()
def list_promotions():
    now = datetime.utcnow()
    promotions = (
        Promotion.query
        .filter(Promotion.status == "ACTIVE", Promotion.end_date.isnot(None), Promotion.end_date > now)
        .order_by(Promotion.created_at.desc())
        .all()
    )
    return jsonify([_promotion_to_dict(p) for p in promotions]), 200


# US-06 - Publicar promoción
@promotions_bp.route("/promotions", methods=["POST"])
@jwt_required()
def create_promotion():
    data = request.get_json(silent=True) or {}
    user_id = get_jwt_identity()

    user = User.query.get(user_id)
    if not _require_restaurant(user):
        return jsonify({"error": "No autorizado. Se requiere rol RESTAURANT"}), 403

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    price_raw = data.get("price")
    stock_raw = data.get("stock")
    image_url = str(data.get("image_url", "")).strip() or None
    # Accept valid_until or end_date as alias
    valid_until_raw = str(data.get("valid_until") or data.get("end_date") or "").strip()

    # Check missing required fields
    missing = []
    if not name:
        missing.append("name")
    if not description:
        missing.append("description")
    if price_raw is None or str(price_raw).strip() == "":
        missing.append("price")
    if stock_raw is None or str(stock_raw).strip() == "":
        missing.append("stock")
    if not valid_until_raw:
        missing.append("valid_until")

    if missing:
        return jsonify({"error": "Faltan campos obligatorios", "missing": missing}), 400

    try:
        price = float(price_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Precio inválido: debe ser un número"}), 400

    if price <= 0:
        return jsonify({"error": "Precio debe ser mayor que 0"}), 400

    try:
        stock = int(stock_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "Stock inválido: debe ser un entero"}), 400

    if stock <= 0:
        return jsonify({"error": "Stock debe ser mayor que 0"}), 400

    if image_url and not _is_valid_image_url(image_url):
        return jsonify({"error": "image_url inválida: debe terminar en .jpg, .jpeg, .png o .webp"}), 400

    try:
        valid_until = datetime.fromisoformat(valid_until_raw)
    except ValueError:
        return jsonify({"error": "valid_until inválido: usa formato ISO (YYYY-MM-DDTHH:MM)"}), 400

    if valid_until <= datetime.utcnow():
        return jsonify({"error": "valid_until debe ser una fecha futura"}), 400

    duplicate = Promotion.query.filter_by(
        restaurant_id=user.id, name=name, status="ACTIVE"
    ).first()
    if duplicate:
        return jsonify({
            "error": "Ya existe una promoción activa con ese nombre",
            "warning": "Nombre duplicado",
            "existing_id": duplicate.id,
        }), 409

    lat = data.get("lat")
    lng = data.get("lng")
    try:
        lat = float(lat) if lat is not None else None
        lng = float(lng) if lng is not None else None
    except (ValueError, TypeError):
        lat = None
        lng = None

    promotion = Promotion(
        name=name,
        description=description,
        price=price,
        stock=stock,
        image_url=image_url if image_url is not None else "",
        start_date=datetime.utcnow(),
        end_date=valid_until,
        restaurant_id=user.id,
        status="ACTIVE",
    )
    if hasattr(promotion, "lat"):
        promotion.lat = lat
    if hasattr(promotion, "lng"):
        promotion.lng = lng

    db.session.add(promotion)
    db.session.commit()

    return jsonify(_promotion_to_dict(promotion)), 201


# US-08 - Reservar por ruta /promotions/<id>/reserve
@promotions_bp.route("/promotions/<promotion_id>/reserve", methods=["POST"])
@jwt_required()
def reserve_promotion(promotion_id):
    user_id = get_jwt_identity()
    return _do_reserve(user_id, promotion_id)


# US-08 - Reservar (endpoint original - mantener compatibilidad)
@promotions_bp.route("/reservations", methods=["POST"])
@jwt_required()
def create_reservation():
    data = request.get_json(silent=True) or {}
    user_id = get_jwt_identity()
    promotion_id = str(data.get("promotion_id", "")).strip()

    if not promotion_id:
        return jsonify({"error": "promotion_id es obligatorio"}), 400

    return _do_reserve(user_id, promotion_id)