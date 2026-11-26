from flask import Flask

from backend.app.blueprints import bp, report

app = Flask(__name__)
app.register_blueprint(bp)
app.register_blueprint(report, url_prefix="/reports")


@app.route("/legacy/ping")
def ping():
    return "pong"


@app.route("/legacy/users/<int:user_id>", methods=["GET", "DELETE"])
def legacy_user(user_id):
    return ""
