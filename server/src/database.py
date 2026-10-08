import sqlite3
import os

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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            username TEXT,
            password TEXT,
            country TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            ip_address TEXT,
            command TEXT,
            current_dir TEXT
        )
    ''')
    
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
            country TEXT
        )
    ''')
    
    cursor_arch.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY,
            timestamp DATETIME,
            ip_address TEXT,
            command TEXT,
            current_dir TEXT
        )
    ''')
    
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
        cursor.execute("SELECT * FROM attacks WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))
        old_attacks = cursor.fetchall()
        
        if old_attacks:
            conn_arch.executemany('''
                INSERT OR IGNORE INTO attacks (id, timestamp, ip_address, username, password, country)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', old_attacks)
            cursor.execute("DELETE FROM attacks WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))

        # --- Archivage des commandes ---
        cursor.execute("SELECT * FROM commands WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))
        old_commands = cursor.fetchall()
        
        if old_commands:
            conn_arch.executemany('''
                INSERT OR IGNORE INTO commands (id, timestamp, ip_address, command, current_dir)
                VALUES (?, ?, ?, ?, ?)
            ''', old_commands)
            cursor.execute("DELETE FROM commands WHERE timestamp < datetime('now', '-' || ? || ' days')", (days,))

        conn_arch.commit()
        conn.commit()
        
        # Optimisation pour libérer l'espace disque sur la base active
        conn.execute("VACUUM")
        
        if old_attacks or old_commands:
            print(f"[*] Archivage réussi : {len(old_attacks)} attaques et {len(old_commands)} commandes déplacées vers archive.db.")
        
    except Exception as e:
        print(f"[-] Erreur lors de l'archivage : {e}")
    finally:
        conn.close()
        conn_arch.close()

def log_attack(ip_address, username, password, country):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO attacks (ip_address, username, password, country)
        VALUES (?, ?, ?, ?)
    ''', (ip_address, username, password, country))
    conn.commit()
    conn.close()

def log_command(ip_address, command, current_dir):
    """Enregistre une commande exécutée dans le faux shell."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO commands (ip_address, command, current_dir)
        VALUES (?, ?, ?)
    ''', (ip_address, command, current_dir))
    conn.commit()
    conn.close()

def get_all_attacks():
    """Récupère l'historique des attaques."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par leur nom
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM attacks ORDER BY timestamp DESC')
    attacks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return attacks

def get_all_commands():
    """Récupère toutes les commandes enregistrées dans le faux shell."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM commands ORDER BY timestamp DESC')
    commands = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return commands

def get_stats():
    """Calcule des statistiques globales pour le dashboard."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Nombre total d'attaques
    cursor.execute('SELECT COUNT(*) FROM attacks')
    total_attacks = cursor.fetchone()[0]
    
    # Nombre d'IPs uniques
    cursor.execute('SELECT COUNT(DISTINCT ip_address) FROM attacks')
    unique_ips = cursor.fetchone()[0]
    
    # Nombre total de commandes capturées
    cursor.execute('SELECT COUNT(*) FROM commands')
    total_commands = cursor.fetchone()[0]
    
    # Top 5 des pays d'origine
    cursor.execute('SELECT country, COUNT(*) as count FROM attacks WHERE country IS NOT NULL GROUP BY country ORDER BY count DESC LIMIT 5')
    top_countries = [{"country": row[0], "count": row[1]} for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_attacks": total_attacks,
        "unique_ips": unique_ips,
        "total_commands": total_commands,
        "top_countries": top_countries
    }