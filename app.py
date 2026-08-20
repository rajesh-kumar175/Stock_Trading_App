from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import yfinance as import pandas as pd
from models import db, User, Portfolio, Watchlist
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trading.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Core Trading Logic ---
def get_stock_data(symbol, period='1mo'):
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period=period)
        if hist.empty:
            return None
        
        # Technical Indicators - Data Analyst Skill
        hist['MA20'] = hist['Close'].rolling(window=20).mean()
        hist['MA50'] = hist['Close'].rolling(window=50).mean()
        hist['Daily_Return'] = hist['Close'].pct_change()
        hist['RSI'] = compute_rsi(hist['Close'])
        
        info = stock.info
        return {
            'history': hist.tail(30).reset_index().to_dict('records'),
            'current_price': hist['Close'].iloc[-1],
            'change': hist['Close'].iloc[-1] - hist['Close'].iloc[-2],
            'change_percent': ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100,
            'name': info.get('shortName', symbol)
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- Routes ---
@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/stock/')
def api_stock(symbol):
    data = get_stock_data(symbol.upper())
    if not data:
        return jsonify({'error': 'Stock not found'}), 404
    # Convert for JSON
    for record in data['history']:
        record['Date'] = record['Date'].isoformat() if hasattr(record['Date'], 'isoformat') else str(record['Date'])
    return jsonify(data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = generate_password_hash(request.form.get('password'))
        if User.query.filter_by(username=username).first():
            return "User exists"
        new_user = User(username=username, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    watchlist = Watchlist.query.filter_by(user_id=current_user.id).all()
    portfolio = Portfolio.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', watchlist=watchlist, portfolio=portfolio, user=current_user)

@app.route('/api/watchlist/add', methods=['POST'])
@login_required
def add_watchlist():
    symbol = request.json.get('symbol','').upper()
    if not symbol:
        return jsonify({'error': 'Symbol required'}), 400
    exists = Watchlist.query.filter_by(user_id=current_user.id, symbol=symbol).first()
    if not exists:
        item = Watchlist(user_id=current_user.id, symbol=symbol)
        db.session.add(item)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
