import sqlite3
import os
import hashlib
from datetime import datetime, timezone
from contextlib import contextmanager
from paths import SERVER_DATA_DIR

DB_PATH = os.path.join(SERVER_DATA_DIR, 'honeypot.db')
ARCHIVE_PATH = os.path.join(SERVER_DATA_DIR, 'archive.db')
ARCHIVE_BATCH_SIZE = 500


@contextmanager
def _connect(path=None):
    if path is None:
        path = DB_PATH
    conn = sqlite3.connect(path, timeout=10)
    try:
        conn.execute('PRAGMA synchronous=NORMAL')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # 1. Initialisation de la base active (honeypot.db)
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
    
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attack_country_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attack_id INTEGER NOT NULL,
                country TEXT NOT NULL
            )
        ''')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_country_updates_attack '
            'ON attack_country_updates(attack_id)'
        )

        # 3. Table pour la réinitialisation de mot de passe
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at DATETIME NOT NULL,
                used INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token)')

        cursor.execute("PRAGMA table_info(commands)")
        command_columns = [col[1] for col in cursor.fetchall()]
        if 'port' not in command_columns:
            cursor.execute("ALTER TABLE commands ADD COLUMN port INTEGER DEFAULT 2222")
    
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_timestamp ON commands(timestamp, id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_attacks_timestamp ON attacks(timestamp, id)')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_commands_timestamp_utc '
            'ON commands(datetime(timestamp), id)'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_attacks_timestamp_utc '
            'ON attacks(datetime(timestamp), id)'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_commands_session '
            'ON commands(ip_address, port, timestamp)'
        )
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS idx_attacks_session '
            'ON attacks(ip_address, port, timestamp)'
        )
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_attacks_ip ON attacks(ip_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_attacks_country ON attacks(country)')

    # 2. Initialisation de la base d'archives (archive.db)
    with _connect(ARCHIVE_PATH) as conn_arch:
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

def archive_old_data(days=30):
    """Déplace les données de plus de X jours vers archive.db et nettoie honeypot.db."""
    if not os.path.exists(DB_PATH) or not os.path.exists(ARCHIVE_PATH):
        return

    moved_attacks = 0
    moved_commands = 0
    with _connect() as conn, _connect(ARCHIVE_PATH) as conn_arch:
        cursor = conn.cursor()
        cutoff = "datetime('now', '-' || ? || ' days')"

        for table, columns in (
            ('attacks', 'id, timestamp, ip_address, username, password, country, port'),
            ('commands', 'id, timestamp, ip_address, command, current_dir, response, port'),
        ):
            while True:
                cursor.execute(
                    f"SELECT {columns} FROM {table} "
                    f"WHERE datetime(timestamp) < {cutoff} ORDER BY id LIMIT ?",
                    (days, ARCHIVE_BATCH_SIZE)
                )
                rows = cursor.fetchall()
                if not rows:
                    break

                placeholders = ', '.join('?' for _ in rows[0])
                conn_arch.executemany(
                    f"INSERT OR IGNORE INTO {table} ({columns}) VALUES ({placeholders})",
                    rows
                )
                conn_arch.commit()
                if table == 'attacks':
                    cursor.executemany(
                        'DELETE FROM attack_country_updates WHERE attack_id = ?',
                        [(row[0],) for row in rows]
                    )
                cursor.executemany(
                    f"DELETE FROM {table} WHERE id = ?",
                    [(row[0],) for row in rows]
                )
                conn.commit()
                if table == 'attacks':
                    moved_attacks += len(rows)
                else:
                    moved_commands += len(rows)

    if moved_attacks or moved_commands:
        with _connect() as conn:
            conn.execute("VACUUM")
        print(
            f"[*] Archivage réussi : {moved_attacks} attaques et "
            f"{moved_commands} commandes déplacées vers archive.db."
        )

def log_attack(ip_address, username, password, country, port=2222):
    with _connect() as conn:
        cursor = conn.execute('''
            INSERT INTO attacks (timestamp, ip_address, username, password, country, port)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (_utc_timestamp(), ip_address, username, password, country, port))
        return cursor.lastrowid

def log_command(ip_address, command, current_dir, response, port=2222):
    """Enregistre une commande exécutée et sa réponse dans le faux shell."""
    with _connect() as conn:
        cursor = conn.execute('''
            INSERT INTO commands (timestamp, ip_address, command, current_dir, response, port)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (_utc_timestamp(), ip_address, command, current_dir, response, port))
        return cursor.lastrowid

def update_attack_country(attack_id, country):
    with _connect() as conn:
        cursor = conn.execute(
            'UPDATE attacks SET country = ? WHERE id = ?',
            (country, attack_id)
        )
        if cursor.rowcount:
            conn.execute(
                'INSERT INTO attack_country_updates (attack_id, country) VALUES (?, ?)',
                (attack_id, country)
            )


def get_country_updates(after_id=None, before_id=None, limit=None):
    query = 'SELECT id, attack_id, country FROM attack_country_updates'
    clauses = []
    params = []
    if after_id is not None:
        clauses.append('id > ?')
        params.append(after_id)
    if before_id is not None:
        clauses.append('id < ?')
        params.append(before_id)
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    query += ' ORDER BY id ASC' if after_id is not None else ' ORDER BY id DESC'
    if limit is not None:
        query += ' LIMIT ?'
        params.append(limit)

    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def get_latest_country_update_id():
    with _connect() as conn:
        return conn.execute(
            'SELECT COALESCE(MAX(id), 0) FROM attack_country_updates'
        ).fetchone()[0]

def _get_records(
    table,
    columns,
    after_id=None,
    before_id=None,
    limit=None,
    port_filter=None
):
    if table not in ('attacks', 'commands'):
        raise ValueError(f"Table non supportée : {table}")

    query = f"SELECT {columns} FROM {table}"
    clauses = []
    params = []
    if after_id is not None:
        clauses.append('id > ?')
        params.append(after_id)
    if before_id is not None:
        clauses.append('id < ?')
        params.append(before_id)
    if port_filter is not None:
        clauses.append('port = ?')
        params.append(port_filter)
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
    if after_id is not None:
        query += ' ORDER BY id ASC'
    elif before_id is not None or limit is not None:
        query += ' ORDER BY id DESC'
    else:
        query += ' ORDER BY datetime(timestamp) DESC, id DESC'
    if limit is not None:
        query += ' LIMIT ?'
        params.append(limit)

    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def get_all_attacks(after_id=None, before_id=None, limit=None, port_filter=None):
    return _get_records(
        'attacks',
        'id, timestamp, ip_address, username, password, country, port',
        after_id,
        before_id,
        limit,
        port_filter
    )

def get_all_commands(after_id=None, before_id=None, limit=None):
    return _get_records(
        'commands',
        'id, timestamp, ip_address, command, current_dir, response, port',
        after_id,
        before_id,
        limit
    )

def get_stats():
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM attacks')
        total_attacks = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(DISTINCT ip_address) FROM attacks')
        unique_ips = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM commands')
        total_commands = cursor.fetchone()[0]
        cursor.execute('''
            SELECT country, COUNT(*) as count
            FROM attacks
            WHERE country IS NOT NULL
            GROUP BY country
            ORDER BY count DESC
        ''')
        top_countries = [{"country": row[0], "count": row[1]} for row in cursor.fetchall()]
    
    return {
        "total_attacks": total_attacks,
        "unique_ips": unique_ips,
        "total_commands": total_commands,
        "top_countries": top_countries
    }

# --- Fonctions utilitaires pour la réinitialisation de mot de passe ---
def _password_reset_token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_password_reset_token(username, token, expires_at):
    with _connect() as conn:
        conn.execute('''
            INSERT INTO password_resets (username, token, expires_at, used)
            VALUES (?, ?, ?, 0)
        ''', (username, _password_reset_token_hash(token), expires_at))

def consume_password_reset_token(token):
    with _connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('''
            SELECT username FROM password_resets
            WHERE token = ? AND used = 0 AND datetime(expires_at) > datetime('now')
        ''', (_password_reset_token_hash(token),)).fetchone()
        if not row:
            return None
        conn.execute(
            'UPDATE password_resets SET used = 1 WHERE username = ? AND used = 0',
            (row[0],)
        )
        return row[0]