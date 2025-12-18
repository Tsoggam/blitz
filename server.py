from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta
import threading
import time
import os

app = Flask(__name__)
CORS(app)

DATABASE = 'blitz.db'
DAILY_CHIPS = 20

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS players (
            username TEXT PRIMARY KEY,
            chips INTEGER NOT NULL,
            last_claim TIMESTAMP NOT NULL,
            total_wins INTEGER DEFAULT 0,
            total_losses INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result TEXT NOT NULL,
            winners TEXT,
            losers TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

@app.route('/api/player/<username>', methods=['GET'])
def get_player(username):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT chips, last_claim FROM players WHERE username = ?', (username,))
    result = c.fetchone()
    
    if result:
        chips, last_claim = result
        last_claim_dt = datetime.fromisoformat(last_claim)
        time_passed = datetime.now() - last_claim_dt
        
        if time_passed >= timedelta(days=1):
            chips = DAILY_CHIPS
            c.execute('UPDATE players SET chips = ?, last_claim = ? WHERE username = ?',
                     (chips, datetime.now().isoformat(), username))
            conn.commit()
        
        conn.close()
        
        time_left = timedelta(days=1) - time_passed
        hours_left = int(time_left.total_seconds() / 3600)
        
        return jsonify({
            'username': username,
            'chips': chips,
            'hours_left': max(0, hours_left)
        })
    else:
        c.execute('INSERT INTO players (username, chips, last_claim) VALUES (?, ?, ?)',
                 (username, DAILY_CHIPS, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        return jsonify({
            'username': username,
            'chips': DAILY_CHIPS,
            'hours_left': 24
        })

@app.route('/api/player/<username>/update', methods=['POST'])
def update_player(username):
    data = request.json
    new_chips = data.get('chips')
    
    if new_chips is None:
        return jsonify({'error': 'Chips não informadas'}), 400
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('UPDATE players SET chips = ? WHERE username = ?', (new_chips, username))
    
    if c.rowcount == 0:
        c.execute('INSERT INTO players (username, chips, last_claim) VALUES (?, ?, ?)',
                 (username, new_chips, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'chips': new_chips})

@app.route('/api/ranking', methods=['GET'])
def get_ranking():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT username, chips FROM players ORDER BY chips DESC LIMIT 10')
    results = c.fetchall()
    conn.close()
    
    ranking = [{'name': row[0], 'chips': row[1]} for row in results]
    return jsonify(ranking)

@app.route('/api/history', methods=['GET'])
def get_history():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('SELECT result, winners, timestamp FROM game_history ORDER BY id DESC LIMIT 10')
    results = c.fetchall()
    conn.close()
    
    history = [{
        'result': row[0],
        'winners': row[1],
        'timestamp': row[2]
    } for row in results]
    
    return jsonify(history)

@app.route('/api/history/add', methods=['POST'])
def add_history():
    data = request.json
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('INSERT INTO game_history (result, winners) VALUES (?, ?)',
             (data['result'], data['winners']))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/batch-update', methods=['POST'])
def batch_update():
    data = request.json
    players_data = data.get('players', [])
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    for player in players_data:
        username = player['username']
        chips = player['chips']
        
        c.execute('UPDATE players SET chips = ? WHERE username = ?', (chips, username))
        
        if c.rowcount == 0:
            c.execute('INSERT INTO players (username, chips, last_claim) VALUES (?, ?, ?)',
                     (username, chips, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'updated': len(players_data)})

@app.route('/api/cleanup', methods=['POST'])
def cleanup_old_data():
    cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('DELETE FROM players WHERE last_claim < ?', (cutoff_date,))
    deleted = c.rowcount
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'deleted': deleted})

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'online', 'timestamp': datetime.now().isoformat()})

@app.route('/', methods=['GET'])
def index():
    return jsonify({'message': 'Blitz API Server', 'status': 'running'})

def auto_cleanup():
    while True:
        time.sleep(86400)
        try:
            cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
            conn = sqlite3.connect(DATABASE)
            c = conn.cursor()
            c.execute('DELETE FROM players WHERE last_claim < ?', (cutoff_date,))
            conn.commit()
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    init_db()
    
    cleanup_thread = threading.Thread(target=auto_cleanup, daemon=True)
    cleanup_thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)