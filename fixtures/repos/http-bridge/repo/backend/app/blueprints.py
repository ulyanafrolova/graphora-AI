from flask import Blueprint

bp = Blueprint("admin", __name__, url_prefix="/admin")
report = Blueprint("report", __name__, url_prefix="/old")


@bp.route("/stats")
def stats():
    return {}


@report.route("/daily")
def daily():
    return {}
