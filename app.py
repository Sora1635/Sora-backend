from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import sqlite3
import secrets
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

def get_db():
    conn = sqlite3.connect('channels.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_username TEXT NOT NULL,
            subscription_verified INTEGER DEFAULT 0,
            last_checked TEXT,
            access_revoked INTEGER DEFAULT 0,
            premium_status INTEGER DEFAULT 0,
            premium_expiry TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS verification_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS subscription_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            subscription_count INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_username TEXT NOT NULL,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )''')
        conn.commit()

init_db()

@app.route('/api/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    data = request.json
    telegram_username = data.get('telegram_username')
    if not telegram_username or not telegram_username.startswith('@'):
        return jsonify({'error': 'Invalid Telegram username'}), 400
    
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE telegram_username = ?', (telegram_username,))
        if c.fetchone():
            return jsonify({'error': 'User already exists'}), 400
        c.execute('INSERT INTO users (telegram_username, last_checked) VALUES (?, ?)',
                  (telegram_username, datetime.now().isoformat()))
        user_id = c.lastrowid
        token = secrets.token_urlsafe(16)
        c.execute('INSERT INTO verification_tokens (user_id, token, created_at) VALUES (?, ?, ?)',
                  (user_id, token, datetime.now().isoformat()))
        conn.commit()
    
    bot_link = f"https://t.me/Piar163Bot?start=verify_{token}"
    return jsonify({'bot_link': bot_link})

@app.route('/api/check_access', methods=['GET'])
def check_access():
    telegram_username = request.args.get('telegram_username')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT subscription_verified, access_revoked FROM users WHERE telegram_username = ?', (telegram_username,))
        user = c.fetchone()
        if not user or user['access_revoked'] or not user['subscription_verified']:
            return jsonify({'access': False}), 403
        return jsonify({'access': True})

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    data = request.json
    telegram_username = data.get('telegram_username')
    channel_username = data.get('channel_username')
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, subscription_verified, premium_status FROM users WHERE telegram_username = ?', (telegram_username,))
        user = c.fetchone()
        if not user or not user['subscription_verified']:
            return jsonify({'error': 'No access'}), 403
        
        c.execute('SELECT COUNT(*) as count FROM subscription_logs WHERE user_id = ? AND date > ?', 
                  (user['id'], (datetime.now() - timedelta(days=1)).isoformat()))
        sub_count = c.fetchone()['count']
        limit = 2000 if user['premium_status'] else 1000
        if sub_count >= limit:
            return jsonify({'error': 'Subscription limit reached'}), 429
        
        c.execute('INSERT INTO channels (channel_username, user_id) VALUES (?, ?)', (channel_username, user['id']))
        c.execute('INSERT INTO subscription_logs (user_id, date, subscription_count) VALUES (?, ?, ?)',
                  (user['id'], datetime.now().isoformat(), sub_count + 1))
        conn.commit()
    
    return jsonify({'message': 'Subscribed successfully'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))