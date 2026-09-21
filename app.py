from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash
import yfinance as yf

from models import Portfolio, User, Watchlist, db


app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trading.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def compute_rsi(prices, period=14):
    delta = prices.diff().fillna(0)
    gain = delta.where(delta > 0, 0).rolling(window=period, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=period).mean()
    rs = gain / loss.replace(0, float("inf"))
    return (100 - (100 / (1 + rs))).fillna(50)


def get_stock_data(symbol, period="1mo"):
    try:
        stock = yf.Ticker(symbol)
        history = stock.history(period=period)
        if history.empty or "Close" not in history:
            return None

        close_prices = history["Close"]
        history["MA20"] = close_prices.rolling(window=20, min_periods=1).mean()
        history["MA50"] = close_prices.rolling(window=50, min_periods=1).mean()
        history["Daily_Return"] = close_prices.pct_change().fillna(0)
        history["RSI"] = compute_rsi(close_prices)

        last_close = float(close_prices.iloc[-1])
        previous_close = float(close_prices.iloc[-2]) if len(close_prices) > 1 else last_close
        change = last_close - previous_close
        change_percent = (change / previous_close * 100) if previous_close else 0

        try:
            name = stock.info.get("shortName", symbol)
        except Exception:
            name = symbol

        records = history.tail(30).reset_index().to_dict("records")
        for record in records:
            for key, value in record.items():
                if hasattr(value, "item"):
                    record[key] = value.item()
                if hasattr(record[key], "isoformat"):
                    record[key] = record[key].isoformat()

        return {
            "history": records,
            "current_price": last_close,
            "change": float(change),
            "change_percent": float(change_percent),
            "name": name,
        }
    except Exception as exc:
        app.logger.warning("Error fetching %s: %s", symbol, exc)
        return None


@app.route("/")
def index():
    return render_template("home.html")


@app.route("/api/stock", methods=["GET"])
@app.route("/api/stock/<symbol>", methods=["GET"])
def api_stock(symbol=None):
    symbol = (symbol or request.args.get("symbol", "")).strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400

    data = get_stock_data(symbol)
    if data is None:
        return jsonify({"error": "Stock not found"}), 404
    return jsonify(data)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not username or not email or not password:
            return render_template("register.html", error="All fields are required")
        if User.query.filter((User.username == username) | (User.email == email)).first():
            return render_template("register.html", error="Username or email already exists")
        db.session.add(User(username=username, email=email, password=generate_password_hash(password)))
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/dashboard")
@login_required
def dashboard():
    watchlist = Watchlist.query.filter_by(user_id=current_user.id).all()
    portfolio = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template("dashboard.html", watchlist=watchlist, portfolio=portfolio, user=current_user)


@app.route("/api/watchlist/add", methods=["POST"])
@login_required
def add_watchlist():
    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400
    if not Watchlist.query.filter_by(user_id=current_user.id, symbol=symbol).first():
        db.session.add(Watchlist(user_id=current_user.id, symbol=symbol))
        db.session.commit()
    return jsonify({"success": True})


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=10000, debug=False)
