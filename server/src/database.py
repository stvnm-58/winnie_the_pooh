import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '../data/honeypot.db')
ARCHIVE_PATH = os.path.join(os.path.dirname(__file__), '../data/archive.db')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # 1. Initialisation de la base active (honeypot.db)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            ip_address TEXT,
            username TEXT,
            password TEXT,
            country TEXT,
            port INTEGER DEFAULT 2222
        )
    ''')
    
    # Migration automatique si la colonne 'port' manque sur une ancienne base active
    cursor.execute("PRAGMA table_info(attacks)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'port' not in columns:
        cursor.execute("ALTER TABLE attacks ADD COLUMN port INTEGER DEFAULT 2222")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            ip_address TEXT,
            command TEXT,
            current_dir TEXT,
            response TEXT,
            port INTEGER DEFAULT 2222
        )
    ''')

    cursor.execute("PRAGMA table_info(commands)")
    command_columns = [col[1] for col in cursor.fetchall()]
    if 'port' not in command_columns:
        cursor.execute("ALTER TABLE commands ADD COLUMN port INTEGER DEFAULT 2222")
    
    # Index pour accélérer les recherches sur la base active
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_timestamp ON commands(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_attacks_timestamp ON attacks(timestamp)')
    
    conn.commit()
    conn.close()

    # 2. Initialisation de la base d'archives (archive.db)
    conn_arch = sqlite3.connect(ARCHIVE_PATH)
    cursor_arch = conn_arch.cursor()
    
    cursor_arch.execute('''
        CREATE TABLE IF NOT EXISTS attacks (
            id INTEGER PRIMARY KEY,
            timestamp DATETIME,
            ip_address TEXT,
            username TEXT,
            password TEXT,
            country TEXT,
            port INTEGER DEFAULT 2222
        )
    ''')

    # Migration automatique si la colonne 'port' manque sur la base d'archives
    cursor_arch.execute("PRAGMA table_info(attacks)")
    arch_columns = [col[1] for col in cursor_arch.fetchall()]
    if 'port' not in arch_columns:
        cursor_arch.execute("ALTER TABLE attacks ADD COLUMN port INTEGER DEFAULT 2222")
    
    cursor_arch.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY,
            timestamp DATETIME,
            ip_address TEXT,
            command TEXT,
            current_dir TEXT,
            response TEXT,
            port INTEGER DEFAULT 2222
        )
    ''')

    cursor_arch.execute("PRAGMA table_info(commands)")
    arch_command_columns = [col[1] for col in cursor_arch.fetchall()]
    if 'port' not in arch_command_columns:
        cursor_arch.execute("ALTER TABLE commands ADD COLUMN port INTEGER DEFAULT 2222")
    
    conn_arch.commit()
    conn_arch.close()

def archive_old_data(days=30):
    """Déplace les données de plus de X jours vers archive.db et nettoie honeypot.db."""
    if not os.path.exists(DB_PATH) or not os.path.exists(ARCHIVE_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    conn_arch = sqlite3.connect(ARCHIVE_PATH)
    
    try:
        cursor = conn.cursor()
        
        # --- Archivage des attaques ---
        cursor.execute("SELECT id, timestamp, ip_address, username, password, country, port FROM attacks WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))
        old_attacks = cursor.fetchall()
        
        if old_attacks:
            conn_arch.executemany('''
                INSERT OR IGNORE INTO attacks (id, timestamp, ip_address, username, password, country, port)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', old_attacks)
            cursor.execute("DELETE FROM attacks WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))

        # --- Archivage des commandes ---
        cursor.execute("SELECT id, timestamp, ip_address, command, current_dir, response, port FROM commands WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))
        old_commands = cursor.fetchall()
        
        if old_commands:
            conn_arch.executemany('''
                INSERT OR IGNORE INTO commands (id, timestamp, ip_address, command, current_dir, response, port)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', old_commands)
            cursor.execute("DELETE FROM commands WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))

        conn_arch.commit()
        conn.commit()
        
        conn.execute("VACUUM")
        
        if old_attacks or old_commands:
            print(f"[*] Archivage réussi : {len(old_attacks)} attaques et {len(old_commands)} commandes déplacées vers archive.db.")
        
    except Exception as e:
        print(f"[-] Erreur lors de l'archivage : {e}")
    finally:
        conn.close()
        conn_arch.close()

def log_attack(ip_address, username, password, country, port=2222):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO attacks (timestamp, ip_address, username, password, country, port)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (current_time, ip_address, username, password, country, port))
    conn.commit()
    conn.close()

def log_command(ip_address, command, current_dir, response, port=2222):
    """Enregistre une commande exécutée et sa réponse dans le faux shell."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        INSERT INTO commands (timestamp, ip_address, command, current_dir, response, port)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (current_time, ip_address, command, current_dir, response, port))
    conn.commit()
    conn.close()

def get_all_attacks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT id, timestamp, ip_address, username, password, country, port FROM attacks ORDER BY timestamp DESC')
    attacks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return attacks

def get_all_commands():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM commands ORDER BY timestamp DESC')
    commands = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return commands

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM attacks')
    total_attacks = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT ip_address) FROM attacks')
    unique_ips = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM commands')
    total_commands = cursor.fetchone()[0]
    
    cursor.execute('SELECT country, COUNT(*) as count FROM attacks WHERE country IS NOT NULL GROUP BY country ORDER BY count DESC LIMIT 5')
    top_countries = [{"country": row[0], "count": row[1]} for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_attacks": total_attacks,
        "unique_ips": unique_ips,
        "total_commands": total_commands,
        "top_countries": top_countries
    }