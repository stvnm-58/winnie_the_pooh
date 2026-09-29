import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '../data/honeypot.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            username TEXT,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

def log_attack(ip_address, username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO attacks (ip_address, username, password)
        VALUES (?, ?, ?)
    ''', (ip_address, username, password))
    conn.commit()
    conn.close()

def get_all_attacks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par leur nom
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM attacks ORDER BY timestamp DESC')
    attacks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return attacks