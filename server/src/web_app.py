import jwt
import datetime
import random
import time
from collections import defaultdict
from flask import Flask, g, jsonify, request
from flask_cors import CORS
import os
import json
import hashlib
import ipaddress
import psutil
import subprocess
import socket
import sys
import tempfile
import threading
import secrets
import smtplib
import sqlite3
import ssl
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import check_password_hash, generate_password_hash
from database import (
    get_all_attacks,
    get_all_commands,
    get_country_updates,
    get_latest_country_update_id,
    get_stats,
    create_password_reset_token,
    consume_password_reset_token
)
from paths import AUTH_CONFIG_PATH, BAN_STATE_PATH, CONFIG_PATH

# --- INITIALISATION DE FLASK EN PREMIER ---
app = Flask(__name__)
ALLOWED_ORIGINS = [
    origin.strip().rstrip('/')
    for origin in os.environ.get(
        'HONEYPOT_ALLOWED_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173'
    ).split(',')
    if origin.strip()
]
JWT_SECRET_KEY = os.environ.get('HONEYPOT_JWT_SECRET', '')
ADMIN_USERNAME = os.environ.get('HONEYPOT_ADMIN_USERNAME', '')
ADMIN_PASSWORD_HASH = os.environ.get('HONEYPOT_ADMIN_PASSWORD_HASH', '')
SESSION_TTL_SECONDS = 8 * 60 * 60
COOKIE_SECURE = os.environ.get('HONEYPOT_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')
PASSWORD_RESET_LOCK = threading.Lock()

CORS(
    app,
    resources={r'/api/*': {'origins': ALLOWED_ORIGINS}},
    supports_credentials=True,
    allow_headers=['Content-Type'],
    methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
)

PUBLIC_API_ENDPOINTS = {
    'auth_status',
    'setup_authentication',
    'login',
    'forgot_password',
    'reset_password'
}


def load_auth_file():
    try:
        with open(AUTH_CONFIG_PATH, 'r', encoding='utf-8') as auth_file:
            configuration = json.load(auth_file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError('Configuration du compte indisponible.') from error
    if not isinstance(configuration, dict):
        raise RuntimeError('Configuration du compte invalide.')
    return configuration


def save_auth_file(configuration):
    auth_dir = os.path.dirname(AUTH_CONFIG_PATH)
    temporary_path = None
    try:
        os.makedirs(auth_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=auth_dir,
            delete=False
        ) as auth_file:
            temporary_path = auth_file.name
            json.dump(configuration, auth_file)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, AUTH_CONFIG_PATH)
    except OSError as error:
        raise RuntimeError('Impossible d’enregistrer la configuration du compte.') from error
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError as error:
                app.logger.warning('Impossible de supprimer un fichier temporaire: %s', error)


def is_valid_email(email):
    if not isinstance(email, str) or len(email) > 254:
        return False
    local_part, separator, domain = email.partition('@')
    return bool(
        separator
        and local_part
        and domain
        and '.' in domain
        and not any(character.isspace() for character in email)
    )


def auth_configuration_is_valid():
    return bool(get_auth_configuration())


def get_auth_configuration():
    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return JWT_SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD_HASH

    try:
        with open(AUTH_CONFIG_PATH, 'r', encoding='utf-8') as auth_file:
            configuration = json.load(auth_file)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        app.logger.error('Impossible de lire la configuration d’authentification: %s', error)
        return None

    if not isinstance(configuration, dict):
        app.logger.error('Le fichier de configuration d’authentification est invalide.')
        return None

    secret = configuration.get('jwt_secret')
    username = configuration.get('admin_username')
    password_hash = configuration.get('admin_password_hash')
    if (
        not isinstance(secret, str)
        or len(secret.encode('utf-8')) < 32
        or not isinstance(username, str)
        or not username
        or not isinstance(password_hash, str)
        or not password_hash
    ):
        app.logger.error('Le fichier de configuration d’authentification est incomplet.')
        return None

    return secret, username, password_hash


@app.before_request
def protect_api():
    if not request.path.startswith('/api/') or request.method == 'OPTIONS':
        return None

    if request.path == '/api/report-attempt':
        return None

    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') not in ALLOWED_ORIGINS:
        return jsonify({'error': 'Origine non autorisée'}), 403
    if request.method not in ('GET', 'HEAD') and origin not in ALLOWED_ORIGINS:
        return jsonify({'error': 'Origine requise ou non autorisée'}), 403

    if request.endpoint in PUBLIC_API_ENDPOINTS:
        return None

    auth_configuration = get_auth_configuration()
    if not auth_configuration:
        return jsonify({'error': 'Authentification non configurée sur le serveur'}), 503
    secret, _, _ = auth_configuration

    token = request.cookies.get('winnie_token')
    if not token:
        return jsonify({'error': 'Jeton d’authentification manquant'}), 401

    try:
        claims = jwt.decode(token, secret, algorithms=['HS256'])
        if not isinstance(claims.get('user'), str) or not claims['user']:
            raise jwt.InvalidTokenError('User claim is missing')
        g.current_user = claims['user']
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Session expirée, veuillez vous reconnecter'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Jeton invalide'}), 401

    return None


@app.route('/api/auth-status', methods=['GET'])
def auth_status():
    if auth_configuration_is_valid():
        return jsonify({'setup_required': False})
    if os.path.exists(AUTH_CONFIG_PATH):
        return jsonify({
            'error': 'Le fichier de configuration du compte administrateur est invalide'
        }), 503
    return jsonify({'setup_required': True})


def create_session_response(username, secret, status=200):
    token = jwt.encode({
        'user': username,
        'exp': datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=SESSION_TTL_SECONDS)
    }, secret, algorithm='HS256')
    response = jsonify({'username': username})
    response.status_code = status
    response.set_cookie(
        'winnie_token',
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.is_secure or COOKIE_SECURE,
        samesite='Lax',
        path='/api'
    )
    return response


@app.route('/api/setup', methods=['POST'])
def setup_authentication():
    if auth_configuration_is_valid():
        return jsonify({'error': 'Le compte administrateur est déjà configuré'}), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps de requête invalide'}), 400
    username = data.get('username')
    password = data.get('password')
    admin_email = data.get('email', '')
    if not isinstance(username, str) or not username.strip() or len(username.strip()) > 64:
        return jsonify({'error': 'Identifiant requis (64 caractères maximum)'}), 400
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        return jsonify({'error': 'Le mot de passe doit contenir entre 12 et 1024 caractères'}), 400
    if admin_email and not is_valid_email(admin_email.strip()):
        return jsonify({'error': 'Adresse e-mail de récupération invalide'}), 400
    if len(ALLOWED_ORIGINS) == 0:
        return jsonify({'error': 'Aucune origine autorisée n’est configurée'}), 503

    configuration = {
        'jwt_secret': secrets.token_urlsafe(48),
        'admin_username': username.strip(),
        'admin_password_hash': generate_password_hash(password)
    }
    if admin_email:
        configuration['admin_email'] = admin_email.strip().lower()
    try:
        os.makedirs(os.path.dirname(AUTH_CONFIG_PATH), exist_ok=True)
        file_descriptor = os.open(
            AUTH_CONFIG_PATH,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600
        )
    except FileExistsError:
        return jsonify({'error': 'Le compte administrateur est déjà configuré'}), 409
    except OSError as error:
        app.logger.error('Impossible de créer la configuration d’authentification: %s', error)
        return jsonify({'error': 'Impossible d’enregistrer le compte administrateur'}), 500

    try:
        with os.fdopen(file_descriptor, 'w', encoding='utf-8') as auth_file:
            json.dump(configuration, auth_file)
        try:
            os.chmod(AUTH_CONFIG_PATH, 0o600)
        except OSError as error:
            app.logger.error('Impossible de protéger le fichier d’authentification: %s', error)
            os.unlink(AUTH_CONFIG_PATH)
            return jsonify({'error': 'Impossible de protéger la configuration du compte'}), 500
    except OSError as error:
        app.logger.error('Impossible d’enregistrer la configuration d’authentification: %s', error)
        try:
            os.unlink(AUTH_CONFIG_PATH)
        except OSError:
            app.logger.exception('Impossible de nettoyer le fichier d’authentification incomplet')
        return jsonify({'error': 'Impossible d’enregistrer le compte administrateur'}), 500

    return create_session_response(
        configuration['admin_username'],
        configuration['jwt_secret'],
        status=201
    )


@app.route('/api/account', methods=['GET', 'PATCH'])
def account_settings():
    try:
        configuration = load_auth_file()
    except RuntimeError as error:
        return jsonify({'error': str(error)}), 503

    if request.method == 'GET':
        recovery_email = configuration.get(
            'admin_email',
            os.environ.get('HONEYPOT_ADMIN_EMAIL', '')
        )
        smtp_user = os.environ.get('HONEYPOT_SMTP_USERNAME') or configuration.get('smtp_user', '')
        smtp_from = os.environ.get('HONEYPOT_SMTP_FROM') or configuration.get('smtp_from', smtp_user)
        smtp_host = os.environ.get('HONEYPOT_SMTP_HOST') or configuration.get('smtp_host', '')
        smtp_port = os.environ.get('HONEYPOT_SMTP_PORT') or configuration.get('smtp_port', 587)
        return jsonify({
            'email': recovery_email if isinstance(recovery_email, str) else '',
            'smtp_host': smtp_host if isinstance(smtp_host, str) else '',
            'smtp_port': str(smtp_port),
            'smtp_user': smtp_user if isinstance(smtp_user, str) else '',
            'smtp_from': smtp_from if isinstance(smtp_from, str) else '',
            'smtp_password_configured': bool(
                os.environ.get('HONEYPOT_SMTP_PASSWORD')
                or configuration.get('smtp_password')
            )
        })

    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return jsonify({
            'error': 'Configurez l’adresse de récupération avec HONEYPOT_ADMIN_EMAIL dans l’environnement du serveur.'
        }), 503

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('email'), str):
        return jsonify({'error': 'Adresse e-mail requise'}), 400
    email = data['email'].strip().lower()
    if not is_valid_email(email):
        return jsonify({'error': 'Adresse e-mail de récupération invalide'}), 400
    configuration['admin_email'] = email

    smtp_host = data.get('smtp_host', configuration.get('smtp_host', ''))
    smtp_port = data.get('smtp_port', configuration.get('smtp_port', 587))
    smtp_user = data.get('smtp_user', configuration.get('smtp_user', ''))
    smtp_from = data.get('smtp_from', configuration.get('smtp_from', smtp_user))
    smtp_password = data.get('smtp_password', '')

    if not all(isinstance(value, str) for value in (smtp_host, smtp_user, smtp_from)):
        return jsonify({'error': 'Configuration SMTP invalide.'}), 400
    smtp_host = smtp_host.strip()
    smtp_user = smtp_user.strip()
    smtp_from = smtp_from.strip().lower()
    if smtp_host and (len(smtp_host) > 253 or any(char.isspace() for char in smtp_host)):
        return jsonify({'error': 'Nom de serveur SMTP invalide.'}), 400
    try:
        smtp_port = int(smtp_port)
    except (TypeError, ValueError):
        return jsonify({'error': 'Le port SMTP doit être compris entre 1 et 65535.'}), 400
    if not 1 <= smtp_port <= 65535:
        return jsonify({'error': 'Le port SMTP doit être compris entre 1 et 65535.'}), 400
    if smtp_from and not is_valid_email(smtp_from):
        return jsonify({'error': 'Adresse d’expéditeur SMTP invalide.'}), 400
    if not isinstance(smtp_password, str) or len(smtp_password) > 1024:
        return jsonify({'error': 'Mot de passe SMTP invalide.'}), 400
    if smtp_password:
        configuration['smtp_password'] = smtp_password
    if smtp_host:
        configuration['smtp_host'] = smtp_host
    else:
        configuration.pop('smtp_host', None)
    if smtp_user:
        configuration['smtp_user'] = smtp_user
    else:
        configuration.pop('smtp_user', None)
    if smtp_from:
        configuration['smtp_from'] = smtp_from
    else:
        configuration.pop('smtp_from', None)
    configuration['smtp_port'] = smtp_port

    try:
        save_auth_file(configuration)
    except RuntimeError as error:
        app.logger.error('Impossible de mettre à jour l’adresse de récupération: %s', error)
        return jsonify({'error': str(error)}), 500
    return jsonify({
        'success': True,
        'email': email,
        'smtp_host': configuration.get('smtp_host', ''),
        'smtp_port': str(configuration.get('smtp_port', 587)),
        'smtp_user': configuration.get('smtp_user', ''),
        'smtp_from': configuration.get('smtp_from', ''),
        'smtp_password_configured': bool(configuration.get('smtp_password'))
    })


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps de requête invalide'}), 400
    username = data.get('username')
    password = data.get('password')

    if (
        not isinstance(username, str)
        or not username
        or not isinstance(password, str)
        or not password
    ):
        return jsonify({'error': 'Identifiant et mot de passe requis'}), 400

    auth_configuration = get_auth_configuration()
    if not auth_configuration:
        return jsonify({'error': 'Authentification non configurée sur le serveur'}), 503
    secret, admin_username, password_hash = auth_configuration

    try:
        password_matches = username == admin_username and check_password_hash(
            password_hash,
            password
        )
    except (TypeError, ValueError) as error:
        app.logger.error('Le hash de mot de passe administrateur est invalide: %s', error)
        return jsonify({'error': 'Configuration du mot de passe invalide'}), 503

    if password_matches:
        return create_session_response(username, secret)

    return jsonify({'error': 'Identifiants incorrects'}), 401


@app.route('/api/session', methods=['GET'])
def get_session():
    return jsonify({'username': g.current_user})


@app.route('/api/logout', methods=['POST'])
def logout():
    response = jsonify({'success': True})
    response.delete_cookie(
        'winnie_token',
        path='/api',
        secure=request.is_secure or COOKIE_SECURE,
        httponly=True,
        samesite='Lax'
    )
    return response


# --- ROUTES DE RÉINITIALISATION DE MOT DE PASSE ---

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('username'), str):
        return jsonify({'error': 'Identifiant invalide'}), 400
    username = data['username'].strip()
    if not username or len(username) > 64:
        return jsonify({'error': 'Identifiant invalide'}), 400

    try:
        auth_config = load_auth_file()
    except RuntimeError as error:
        app.logger.error('Impossible de lire la configuration du compte: %s', error)
        return jsonify({'error': 'Authentification non configurée'}), 503

    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return jsonify({
            'error': 'La récupération par e-mail n’est pas disponible lorsque l’authentification est fournie par variables d’environnement.'
        }), 503
    auth_configuration = get_auth_configuration()
    if not auth_configuration:
        return jsonify({'error': 'Authentification non configurée'}), 503
    _, admin_username, _ = auth_configuration
    admin_email = auth_config.get(
        'admin_email',
        os.environ.get('HONEYPOT_ADMIN_EMAIL', '')
    )

    if username != admin_username or not is_valid_email(admin_email):
        return jsonify({
            'success': True,
            'message': 'Si un compte est associé à cet identifiant, un lien de réinitialisation a été envoyé.'
        })

    smtp_host = os.environ.get('HONEYPOT_SMTP_HOST') or auth_config.get('smtp_host', '')
    smtp_user = os.environ.get('HONEYPOT_SMTP_USERNAME') or auth_config.get('smtp_user', '')
    smtp_password = os.environ.get('HONEYPOT_SMTP_PASSWORD') or auth_config.get('smtp_password', '')
    smtp_from = os.environ.get('HONEYPOT_SMTP_FROM') or auth_config.get('smtp_from', smtp_user)
    smtp_port_value = os.environ.get('HONEYPOT_SMTP_PORT') or auth_config.get('smtp_port', 587)

    if not is_valid_email(admin_email):
        admin_email = ''
    try:
        smtp_port = int(smtp_port_value)
        if not 1 <= smtp_port <= 65535:
            raise ValueError('Port SMTP hors plage.')
    except (TypeError, ValueError):
        return jsonify({'error': 'Configuration SMTP invalide.'}), 503
    if not all(
        isinstance(value, str) and value
        for value in (smtp_host, smtp_user, smtp_password, smtp_from)
    ):
        return jsonify({'error': 'Le service e-mail de récupération n’est pas configuré.'}), 503

    origin = request.headers.get('Origin', '').rstrip('/')
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15)
    ).strftime('%Y-%m-%d %H:%M:%S')
    try:
        create_password_reset_token(admin_username, token, expires_at)
        reset_link = f'{origin}/?token={quote(token)}'
        message = MIMEMultipart()
        message['From'] = smtp_from
        message['To'] = admin_email
        message['Subject'] = 'Réinitialisation de votre mot de passe - Honeypot Swarm'
        message.attach(MIMEText(
            'Bonjour,\n\n'
            f'Voici votre lien de réinitialisation (valable 15 minutes) :\n{reset_link}\n\n'
            'Si vous n’êtes pas à l’origine de cette demande, ignorez ce message.',
            'plain'
        ))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                timeout=10,
                context=ssl.create_default_context()
            ) as mail_server:
                mail_server.login(smtp_user, smtp_password)
                mail_server.sendmail(smtp_from, admin_email, message.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as mail_server:
                mail_server.starttls(context=ssl.create_default_context())
                mail_server.login(smtp_user, smtp_password)
                mail_server.sendmail(smtp_from, admin_email, message.as_string())
    except (OSError, RuntimeError, sqlite3.Error, smtplib.SMTPException) as error:
        app.logger.error('Échec de l’envoi de l’e-mail de récupération: %s', error)
        return jsonify({'error': 'Impossible d’envoyer le lien de récupération.'}), 502

    return jsonify({
        'success': True,
        'message': 'Si un compte est associé à cet identifiant, un lien de réinitialisation a été envoyé.'
    })


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps de requête invalide'}), 400

    token = data.get('token')
    new_password = data.get('password')

    if (
        not isinstance(token, str)
        or not token
        or len(token) > 256
        or not isinstance(new_password, str)
        or not 12 <= len(new_password) <= 1024
    ):
        return jsonify({'error': 'Token invalide ou mot de passe trop court (12 caractères min)'}), 400

    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return jsonify({
            'error': 'La réinitialisation par e-mail n’est pas disponible lorsque l’authentification est fournie par variables d’environnement.'
        }), 503

    with PASSWORD_RESET_LOCK:
        try:
            reset_username = consume_password_reset_token(token)
        except sqlite3.Error as error:
            app.logger.error('Impossible de valider le jeton de récupération: %s', error)
            return jsonify({'error': 'Impossible de valider le lien de récupération.'}), 500
        if not reset_username:
            return jsonify({'error': 'Le lien de réinitialisation est invalide ou a expiré.'}), 400
        try:
            config = load_auth_file()
            if config.get('admin_username') != reset_username:
                return jsonify({'error': 'Le lien de réinitialisation est invalide ou a expiré.'}), 400
            config['admin_password_hash'] = generate_password_hash(new_password)
            config['jwt_secret'] = secrets.token_urlsafe(48)
            save_auth_file(config)
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            app.logger.error('Erreur lors de la mise à jour du mot de passe: %s', error)
            return jsonify({'error': 'Impossible de mettre à jour le mot de passe.'}), 500

    return jsonify({'success': True, 'message': 'Mot de passe réinitialisé avec succès.'})


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT_CHANGE_LOCK = threading.Lock()
BAN_LOCK = threading.Lock()
HONEYPOT_LOCK = threading.Lock()
MAX_API_PAGE_SIZE = 500

# --- STRUCTURES POUR L'AUTO-BAN (RATE LIMITING & STATS) ---
ATTEMPT_HISTORY = defaultdict(list)
AUTO_BAN_STATS = {} 
AUTO_BAN_ENABLED = True
RATE_LIMIT_WINDOW = 15     
RATE_LIMIT_MAX_ATTEMPTS = 15 

def get_current_port():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        return 2222
    except (OSError, json.JSONDecodeError) as error:
        print(f"[-] Impossible de lire la configuration du port ({error}); port 2222 utilisé.")
        return 2222

    if isinstance(config, dict):
        port = config.get('port', 2222)
        if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
            return port
    print("[-] Configuration du port invalide; port 2222 utilisé.")
    return 2222

def save_configured_port(port):
    config_dir = os.path.dirname(CONFIG_PATH)
    os.makedirs(config_dir, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=config_dir,
            delete=False
        ) as config_file:
            temp_path = config_file.name
            json.dump({"port": port}, config_file)
        os.replace(temp_path, CONFIG_PATH)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

def find_honeypot_processes(honeypot_script):
    target_script = os.path.normcase(os.path.abspath(honeypot_script))
    honeypot_processes = []
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if proc.pid == os.getpid():
                continue
            cmdline = proc.info.get('cmdline') or []
            if any(
                os.path.normcase(os.path.abspath(argument)) == target_script
                for argument in cmdline
                if argument.lower().endswith('.py')
            ):
                honeypot_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return honeypot_processes

def get_honeypot_process_port(process, honeypot_script):
    cmdline = process.info.get('cmdline') or []
    target_script = os.path.normcase(os.path.abspath(honeypot_script))
    for index, argument in enumerate(cmdline):
        if (
            argument.lower().endswith('.py')
            and os.path.normcase(os.path.abspath(argument)) == target_script
        ):
            if index + 1 < len(cmdline) and cmdline[index + 1].isdecimal():
                return int(cmdline[index + 1])
            return get_current_port()
    return None

def stop_honeypot_processes(processes):
    running_processes = []
    for proc in processes:
        try:
            proc.terminate()
            running_processes.append(proc)
        except psutil.NoSuchProcess:
            continue

    for proc in running_processes:
        try:
            proc.wait(timeout=3)
        except psutil.NoSuchProcess:
            continue
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)

def start_honeypot(honeypot_script, port=None, *, archive=True):
    cmd = [sys.executable, honeypot_script]
    if port:
        cmd.append(str(port))
    if not archive:
        cmd.append('--no-archive')
    process = subprocess.Popen(cmd, cwd=BASE_DIR)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        return process
    raise RuntimeError(
        f"Le processus honeypot s'est arrêté au démarrage (code {process.returncode})."
    )


def get_record_page_parameters():
    parameters = {}
    for name in ('after_id', 'before_id', 'limit', 'port'):
        raw_value = request.args.get(name)
        if raw_value is None:
            parameters[name] = None
            continue
        if not raw_value.isdecimal():
            raise ValueError(f"Le paramètre '{name}' doit être un entier positif.")
        value = int(raw_value)
        if name == 'limit' and not 1 <= value <= MAX_API_PAGE_SIZE:
            raise ValueError(
                f"Le paramètre 'limit' doit être compris entre 1 et {MAX_API_PAGE_SIZE}."
            )
        if name == 'port' and not 1 <= value <= 65535:
            raise ValueError("Le port doit être compris entre 1 et 65535.")
        parameters[name] = value
    if parameters['after_id'] is not None and parameters['before_id'] is not None:
        raise ValueError("Les curseurs 'after_id' et 'before_id' ne peuvent pas être combinés.")
    return parameters


# --- ROUTES DE STATUT ET DE DONNÉES DU DASHBOARD ---

@app.route('/api/status', methods=['GET'])
def api_status():
    """Fournit l'état global du service et la liste des ports actifs pour le bouton indicateur."""
    instances = find_all_honeypot_instances()
    is_active = len(instances) > 0
    return jsonify({
        "status": "active" if is_active else "inactive",
        "active": is_active,
        "instances": instances,
        "count": len(instances)
    })

@app.route('/api/attacks', methods=['GET'])
def api_attacks():
    """Renvoie une page d'attaques au format attendu par le dashboard."""
    try:
        parameters = get_record_page_parameters()
        attacks = get_all_attacks(
            after_id=parameters['after_id'],
            before_id=parameters['before_id'],
            limit=parameters['limit'],
            port_filter=parameters['port']
        )
        return jsonify(attacks)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception('Impossible de récupérer les attaques.')
        return jsonify({"error": "Impossible de récupérer les attaques."}), 500

@app.route('/api/commands', methods=['GET'])
def api_commands():
    """Renvoie une page de commandes au format attendu par le dashboard."""
    try:
        parameters = get_record_page_parameters()
        commands = get_all_commands(
            after_id=parameters['after_id'],
            before_id=parameters['before_id'],
            limit=parameters['limit']
        )
        return jsonify(commands)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception('Impossible de récupérer les commandes.')
        return jsonify({"error": "Impossible de récupérer les commandes."}), 500


@app.route('/api/country-updates/latest', methods=['GET'])
def api_latest_country_update():
    return jsonify({"id": get_latest_country_update_id()})


@app.route('/api/country-updates', methods=['GET'])
def api_country_updates():
    try:
        parameters = get_record_page_parameters()
        updates = get_country_updates(
            after_id=parameters['after_id'],
            before_id=parameters['before_id'],
            limit=parameters['limit']
        )
        return jsonify(updates)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception('Impossible de récupérer les mises à jour de pays.')
        return jsonify({"error": "Impossible de récupérer les mises à jour de pays."}), 500

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Renvoie les statistiques globales des attaques."""
    try:
        stats = get_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- ROUTES DE GESTION DU DECEPTION MESH (MULTI-HONEYPOTS) ---

def find_all_honeypot_instances():
    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    instances = []
    for proc in find_honeypot_processes(honeypot_script):
        try:
            port = get_honeypot_process_port(proc, honeypot_script)
            if port is not None:
                instances.append({"pid": proc.pid, "port": port})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return sorted(instances, key=lambda instance: (instance['port'], instance['pid']))

@app.route('/api/honeypots', methods=['GET'])
def api_list_honeypots():
    return jsonify({"honeypots": find_all_honeypot_instances()})

@app.route('/api/honeypots', methods=['POST'])
def api_start_honeypot():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or 'port' not in data:
        return jsonify({"error": "Port manquant."}), 400
    value = data['port']
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return jsonify({"error": "Le port doit être un nombre entier."}), 400
    if isinstance(value, str) and (not value.isdecimal() or len(value) > 5):
        return jsonify({"error": "Le port doit être un nombre entier."}), 400
    port = int(value)

    if not 1 <= port <= 65535:
        return jsonify({"error": "Le port doit être compris entre 1 et 65535."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    with HONEYPOT_LOCK:
        if any(instance['port'] == port for instance in find_all_honeypot_instances()):
            return jsonify({"error": f"Un honeypot écoute déjà sur le port {port}."}), 409

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("0.0.0.0", port))
        except OSError:
            return jsonify({"error": f"Le port {port} est déjà utilisé ou indisponible."}), 409

        try:
            process = start_honeypot(honeypot_script, port=port, archive=False)
        except (OSError, RuntimeError) as error:
            return jsonify({"error": f"Échec du lancement du honeypot : {error}"}), 500

    return jsonify({
        "success": True,
        "message": f"Faux SSH déployé avec succès sur le port {port}.",
        "pid": process.pid,
        "port": port
    })

@app.route('/api/honeypots/swarm', methods=['POST'])
def api_start_swarm():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Corps de requête invalide."}), 400
    
    count_val = data.get('count')
    min_val = data.get('port_min')
    max_val = data.get('port_max')

    try:
        count = int(count_val)
        port_min = int(min_val)
        port_max = int(max_val)
    except (TypeError, ValueError):
        return jsonify({"error": "Les paramètres 'count', 'port_min' et 'port_max' doivent être des nombres entiers."}), 400

    if not (1 <= count <= 10):
        return jsonify({"error": "Le nombre de honeypots doit être compris entre 1 et 10."}), 400
    if not (1 <= port_min <= 65535 and 1 <= port_max <= 65535 and port_min <= port_max):
        return jsonify({"error": "La plage de ports est invalide (1-65535)."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    
    with HONEYPOT_LOCK:
        active_ports = {instance['port'] for instance in find_all_honeypot_instances()}
        
        available_ports = []
        for p in range(port_min, port_max + 1):
            if p not in active_ports:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                        probe.bind(("0.0.0.0", p))
                    available_ports.append(p)
                except OSError:
                    continue

        if len(available_ports) < count:
            return jsonify({
                "error": f"Capacité insuffisante : Seulement {len(available_ports)} ports disponibles trouvés dans la plage [{port_min}, {port_max}] pour {count} demandés."
            }), 409

        selected_ports = random.sample(available_ports, count)
        deployed_instances = []
        errors = []

        for p in selected_ports:
            try:
                process = start_honeypot(honeypot_script, port=p, archive=False)
                deployed_instances.append({"port": p, "pid": process.pid})
            except (OSError, RuntimeError) as error:
                errors.append(f"Port {p}: {str(error)}")

    return jsonify({
        "success": True,
        "deployed": deployed_instances,
        "errors": errors,
        "message": f"{len(deployed_instances)} faux SSH déployés en essaim avec succès."
    })

@app.route('/api/honeypots/swarm-reference', methods=['POST'])
def api_start_swarm_reference():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Corps de requête invalide."}), 400
    
    count_val = data.get('count')
    ref_val = data.get('reference_port')

    try:
        count = int(count_val)
        ref_port = int(ref_val)
    except (TypeError, ValueError):
        return jsonify({"error": "Les paramètres 'count' et 'reference_port' doivent être des nombres entiers."}), 400

    if not (1 <= count <= 10):
        return jsonify({"error": "Le nombre de honeypots doit être compris entre 1 et 10."}), 400
    if not (1 <= ref_port <= 65535):
        return jsonify({"error": "Le port de référence doit être compris entre 1 et 65535."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    
    with HONEYPOT_LOCK:
        active_ports = {instance['port'] for instance in find_all_honeypot_instances()}
        
        candidate_ports = []
        offset = 1
        while len(candidate_ports) < (count * 3):
            p_up = ref_port + offset
            p_down = ref_port - offset
            if p_up <= 65535 and p_up != ref_port:
                candidate_ports.append(p_up)
            if p_down >= 1 and p_down != ref_port:
                candidate_ports.append(p_down)
            if p_up > 65535 and p_down < 1:
                break
            offset += 1

        available_ports = []
        for p in candidate_ports:
            if len(available_ports) >= count:
                break
            if p in active_ports:
                continue
            
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind(("0.0.0.0", p))
                available_ports.append(p)
            except OSError:
                continue

        if len(available_ports) < count:
            return jsonify({
                "error": f"Impossible de trouver {count} ports libres autour du service {ref_port}. Seulement {len(available_ports)} disponibles."
            }), 409

        deployed_instances = []
        errors = []

        for p in available_ports:
            try:
                process = start_honeypot(honeypot_script, port=p, archive=False)
                deployed_instances.append({"port": p, "pid": process.pid})
            except (OSError, RuntimeError) as error:
                errors.append(f"Port {p}: {str(error)}")

    return jsonify({
        "success": True,
        "deployed": deployed_instances,
        "errors": errors,
        "message": f"{len(deployed_instances)} honeypots déployés autour du service sur le port {ref_port} avec succès."
    })

@app.route('/api/honeypots/<int:port>', methods=['DELETE'])
def api_stop_honeypot(port):
    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    with HONEYPOT_LOCK:
        matches = [
            proc for proc in find_honeypot_processes(honeypot_script)
            if get_honeypot_process_port(proc, honeypot_script) == port
        ]
        if not matches:
            return jsonify({"error": f"Aucun faux SSH actif trouvé sur le port {port}."}), 404

        try:
            stop_honeypot_processes(matches)
        except (psutil.Error, OSError) as error:
            return jsonify({"error": f"Impossible d'arrêter le honeypot sur le port {port} : {error}"}), 500

    return jsonify({"success": True, "message": f"Faux SSH sur le port {port} arrêté avec succès."})


# --- FONCTIONS DE DÉFENSE ACTIVE (FIREWALL) ---

def run_firewall_command(command, check=True):
    if os.name != 'nt' and os.geteuid() != 0:
        command = ['sudo', '-n', *command]

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Impossible d'exécuter {command[0]} : {error}") from error

    if check and result.returncode:
        details = result.stderr.strip() or result.stdout.strip() or f"code {result.returncode}"
        raise RuntimeError(details)
    return result

def windows_firewall_rule_name(ip_address):
    digest = hashlib.sha256(ip_address.encode('ascii')).hexdigest()[:16]
    return f"WinnieThePooh-Honeypot-{digest}"

def linux_firewall_command(ip_address):
    return 'iptables' if ipaddress.ip_address(ip_address).version == 4 else 'ip6tables'

def linux_rule_exists(command, chain, ip_address):
    result = run_firewall_command(
        [command, '-C', chain, '-s', ip_address, '-j', 'DROP'],
        check=False
    )
    return result.returncode == 0

def load_banned_ips():
    if not os.path.exists(BAN_STATE_PATH):
        return []
    try:
        with open(BAN_STATE_PATH, 'r', encoding='utf-8') as state_file:
            ips = json.load(state_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Impossible de lire l'état des IP bannies : {error}") from error
    if not isinstance(ips, list) or any(not isinstance(ip, str) for ip in ips):
        raise RuntimeError("Le fichier d'état des IP bannies est invalide.")
    return ips

def save_banned_ips(ips):
    state_dir = os.path.dirname(BAN_STATE_PATH)
    temp_path = None
    try:
        os.makedirs(state_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=state_dir,
            delete=False
        ) as state_file:
            temp_path = state_file.name
            json.dump(sorted(set(ips)), state_file)
        os.replace(temp_path, BAN_STATE_PATH)
    except OSError as error:
        raise RuntimeError(f"Impossible d'enregistrer l'état des IP bannies : {error}") from error
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

def ban_ip_system(ip_address):
    parsed_ip = ipaddress.ip_address(ip_address)
    ip_address = str(parsed_ip)
    if os.name == 'nt':
        run_firewall_command([
            'netsh', 'advfirewall', 'firewall', 'add', 'rule',
            f"name={windows_firewall_rule_name(ip_address)}",
            'dir=in', 'action=block', f"remoteip={ip_address}", 'enable=yes'
        ])
        return

    command = linux_firewall_command(ip_address)
    chain = 'WINNIE_HONEYPOT'
    run_firewall_command([command, '-N', chain], check=False)
    run_firewall_command([command, '-S', chain])
    input_jump = run_firewall_command(
        [command, '-C', 'INPUT', '-j', chain],
        check=False
    )
    if input_jump.returncode:
        run_firewall_command([command, '-I', 'INPUT', '1', '-j', chain])
    if not linux_rule_exists(command, chain, ip_address):
        run_firewall_command([command, '-A', chain, '-s', ip_address, '-j', 'DROP'])

def unban_ip_system(ip_address):
    parsed_ip = ipaddress.ip_address(ip_address)
    ip_address = str(parsed_ip)
    if os.name == 'nt':
        run_firewall_command([
            'netsh', 'advfirewall', 'firewall', 'delete', 'rule',
            f"name={windows_firewall_rule_name(ip_address)}"
        ])
        return

    command = linux_firewall_command(ip_address)
    run_firewall_command([command, '-S', 'INPUT'])
    for chain in ('WINNIE_HONEYPOT', 'INPUT'):
        while linux_rule_exists(command, chain, ip_address):
            run_firewall_command([command, '-D', chain, '-s', ip_address, '-j', 'DROP'])

@app.route('/api/ban', methods=['POST'])
def api_ban_ip():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('ip'), str):
        return jsonify({"error": "Adresse IP manquante."}), 400
    try:
        parsed_ip = ipaddress.ip_address(data['ip'].strip())
    except ValueError:
        return jsonify({"error": "L'adresse IP fournie est invalide."}), 400
    if parsed_ip.is_loopback:
        return jsonify({
            "error": "Une adresse loopback (127.0.0.1 ou ::1) ne peut pas être bannie."
        }), 400
    target_ip = str(parsed_ip)

    try:
        with BAN_LOCK:
            ban_ip_system(target_ip)
            banned_ips = load_banned_ips()
            if target_ip not in banned_ips:
                banned_ips.append(target_ip)
                save_banned_ips(banned_ips)
    except RuntimeError as error:
        return jsonify({"error": f"Échec du bannissement de l'IP {target_ip} : {error}"}), 500

    return jsonify({"success": True, "message": f"IP {target_ip} bannie avec succès du pare-feu."})

@app.route('/api/unban', methods=['POST'])
def api_unban_ip():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('ip'), str):
        return jsonify({"error": "Adresse IP manquante."}), 400
    try:
        target_ip = str(ipaddress.ip_address(data['ip'].strip()))
    except ValueError:
        return jsonify({"error": "L'adresse IP fournie est invalide."}), 400

    try:
        with BAN_LOCK:
            unban_ip_system(target_ip)
            save_banned_ips([ip for ip in load_banned_ips() if ip != target_ip])
            if target_ip in AUTO_BAN_STATS:
                del AUTO_BAN_STATS[target_ip]
    except RuntimeError as error:
        return jsonify({"error": f"Échec du débannissement de l'IP {target_ip} : {error}"}), 500

    return jsonify({"success": True, "message": f"IP {target_ip} débannie avec succès du pare-feu."})

@app.route('/api/banned-ips', methods=['GET'])
def api_banned_ips():
    try:
        return jsonify({"ips": load_banned_ips()})
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 500

@app.route('/api/autoban-stats', methods=['GET'])
def api_autoban_stats():
    with BAN_LOCK:
        return jsonify({"autoban_stats": AUTO_BAN_STATS})

@app.route('/api/autoban-config', methods=['GET', 'POST'])
def api_autoban_config():
    global AUTO_BAN_ENABLED, RATE_LIMIT_WINDOW, RATE_LIMIT_MAX_ATTEMPTS
    if request.method == 'GET':
        return jsonify({
            "enabled": AUTO_BAN_ENABLED,
            "window": RATE_LIMIT_WINDOW,
            "max_attempts": RATE_LIMIT_MAX_ATTEMPTS
        })
    
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Corps de requête invalide."}), 400

    with BAN_LOCK:
        if 'enabled' in data:
            AUTO_BAN_ENABLED = bool(data['enabled'])
        if 'window' in data:
            try:
                val = int(data['window'])
                if 1 <= val <= 300:
                    RATE_LIMIT_WINDOW = val
            except (ValueError, TypeError):
                pass
        if 'max_attempts' in data:
            try:
                val = int(data['max_attempts'])
                if 1 <= val <= 100:
                    RATE_LIMIT_MAX_ATTEMPTS = val
            except (ValueError, TypeError):
                pass

    return jsonify({
        "success": True,
        "enabled": AUTO_BAN_ENABLED,
        "window": RATE_LIMIT_WINDOW,
        "max_attempts": RATE_LIMIT_MAX_ATTEMPTS
    })

@app.route('/api/attempt-stats', methods=['GET'])
def api_attempt_stats():
    now = time.time()
    with BAN_LOCK:
        active_attempts = {}
        for ip, timestamps in ATTEMPT_HISTORY.items():
            valid_ts = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
            if valid_ts:
                active_attempts[ip] = len(valid_ts)
        return jsonify({"active_attempts": active_attempts})

@app.route('/api/report-attempt', methods=['POST'])
def api_report_attempt():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('ip'), str):
        return jsonify({"error": "IP manquante."}), 400

    try:
        parsed_ip = ipaddress.ip_address(data['ip'].strip())
        if parsed_ip.is_loopback:
            return jsonify({"success": True, "ignored": "loopback"})
        target_ip = str(parsed_ip)
    except ValueError:
        return jsonify({"error": "IP invalide."}), 400

    now = time.time()
    with BAN_LOCK:
        banned_ips = load_banned_ips()
        if target_ip in banned_ips:
            return jsonify({"success": True, "status": "already_banned"})

        timestamps = ATTEMPT_HISTORY[target_ip]
        timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
        timestamps.append(now)
        ATTEMPT_HISTORY[target_ip] = timestamps
        current_attempts = len(timestamps)

        if AUTO_BAN_ENABLED and current_attempts >= RATE_LIMIT_MAX_ATTEMPTS:
            try:
                ban_ip_system(target_ip)
                if target_ip not in banned_ips:
                    banned_ips.append(target_ip)
                    save_banned_ips(banned_ips)
                
                AUTO_BAN_STATS[target_ip] = current_attempts
            except RuntimeError as error:
                app.logger.error(f"Échec auto-ban IP {target_ip} : {error}")

    return jsonify({"success": True, "current_attempts": current_attempts})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)