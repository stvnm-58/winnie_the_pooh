import jwt
import datetime
import random
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
from werkzeug.security import check_password_hash, generate_password_hash
from database import (
    get_all_attacks,
    get_all_commands,
    get_country_updates,
    get_latest_country_update_id,
    get_stats
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

CORS(
    app,
    resources={r'/api/*': {'origins': ALLOWED_ORIGINS}},
    supports_credentials=True,
    allow_headers=['Content-Type'],
    methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
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

    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') not in ALLOWED_ORIGINS:
        return jsonify({'error': 'Origine non autorisée'}), 403
    if request.method not in ('GET', 'HEAD') and origin not in ALLOWED_ORIGINS:
        return jsonify({'error': 'Origine requise ou non autorisée'}), 403

    if request.endpoint in ('login', 'setup_authentication', 'auth_status'):
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
    if not isinstance(username, str) or not username.strip() or len(username.strip()) > 64:
        return jsonify({'error': 'Identifiant requis (64 caractères maximum)'}), 400
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        return jsonify({'error': 'Le mot de passe doit contenir entre 12 et 1024 caractères'}), 400
    if len(ALLOWED_ORIGINS) == 0:
        return jsonify({'error': 'Aucune origine autorisée n’est configurée'}), 503

    configuration = {
        'jwt_secret': secrets.token_urlsafe(48),
        'admin_username': username.strip(),
        'admin_password_hash': generate_password_hash(password)
    }
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT_CHANGE_LOCK = threading.Lock()
BAN_LOCK = threading.Lock()
HONEYPOT_LOCK = threading.Lock()
MAX_API_PAGE_SIZE = 500

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

# --- ROUTES DE GESTION DU DECEPTION MESH (MULTI-HONEYPOTS) ---

def find_all_honeypot_instances():
    """Détecte tous les processus honeypot.py en cours avec leur port exact."""
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
    """Liste tous les faux SSH actifs sur le serveur."""
    return jsonify({"honeypots": find_all_honeypot_instances()})

@app.route('/api/honeypots', methods=['POST'])
def api_start_honeypot():
    """Déploie un nouveau faux SSH sur un port spécifique."""
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
    """Déploie X honeypots sur des ports aléatoires compris entre port_min et port_max."""
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

    if not (1 <= count <= 100):
        return jsonify({"error": "Le nombre de honeypots (count) doit être compris entre 1 et 100."}), 400
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

@app.route('/api/honeypots/<int:port>', methods=['DELETE'])
def api_stop_honeypot(port):
    """Arrête le faux SSH ciblé sur un port précis."""
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

# --- FONCTIONS DE DÉFENSE ACTIVE (FIREWALL : BAN / UNBAN) ---
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
    except RuntimeError as error:
        return jsonify({"error": f"Échec du débannissement de l'IP {target_ip} : {error}"}), 500

    return jsonify({"success": True, "message": f"IP {target_ip} débannie avec succès du pare-feu."})

@app.route('/api/banned-ips', methods=['GET'])
def api_banned_ips():
    try:
        return jsonify({"ips": load_banned_ips()})
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 500
# -----------------------------------------------------------

@app.route('/api/attacks', methods=['GET'])
def api_attacks():
    query, error = get_record_query_params()
    if error:
        return jsonify({"error": error}), 400
    attacks = get_all_attacks(**query)
    return jsonify(attacks)

@app.route('/api/commands', methods=['GET'])
def api_commands():
    query, error = get_record_query_params()
    if error:
        return jsonify({"error": error}), 400
    commands = get_all_commands(**query)
    return jsonify(commands)

@app.route('/api/country-updates/latest', methods=['GET'])
def api_latest_country_update():
    return jsonify({"id": get_latest_country_update_id()})

@app.route('/api/country-updates', methods=['GET'])
def api_country_updates():
    query, error = get_record_query_params()
    if error:
        return jsonify({"error": error}), 400
    return jsonify(get_country_updates(**query))


def get_record_query_params():
    query = {}
    for name in ('after_id', 'before_id'):
        value = request.args.get(name)
        if value is None:
            continue
        if not value.isdecimal() or len(value) > 19:
            return None, f"{name} doit être un entier positif."
        parsed_value = int(value)
        if parsed_value > 9223372036854775807:
            return None, f"{name} est trop grand."
        query[name] = parsed_value

    if 'after_id' in query and 'before_id' in query:
        return None, "after_id et before_id ne peuvent pas être utilisés ensemble."

    limit = request.args.get('limit')
    if limit is None:
        query['limit'] = MAX_API_PAGE_SIZE
    else:
        if (
            not limit.isdecimal()
            or len(limit) > 3
            or not 1 <= int(limit) <= MAX_API_PAGE_SIZE
        ):
            return None, f"limit doit être compris entre 1 et {MAX_API_PAGE_SIZE}."
        query['limit'] = int(limit)
    return query, None

@app.route('/api/stats', methods=['GET'])
def api_stats():
    stats = get_stats()
    return jsonify(stats)

@app.route('/api/status', methods=['GET'])
def api_status():
    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    return jsonify({"active": bool(find_honeypot_processes(honeypot_script))})

@app.route('/api/port', methods=['GET'])
def api_get_port():
    return jsonify({"port": get_current_port()})

@app.route('/api/port', methods=['POST'])
def api_set_port():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Port invalide"}), 400
    value = data.get('port')
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return jsonify({"error": "Le port doit être un entier entre 1 et 65535."}), 400
    if isinstance(value, str) and (not value.isdecimal() or len(value) > 5):
        return jsonify({"error": "Le port doit être un entier entre 1 et 65535."}), 400

    new_port = int(value)
    if not 1 <= new_port <= 65535:
        return jsonify({"error": "Le port doit être compris entre 1 et 65535."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    with PORT_CHANGE_LOCK, HONEYPOT_LOCK:
        old_port = get_current_port()
        old_processes = [
            proc for proc in find_honeypot_processes(honeypot_script)
            if get_honeypot_process_port(proc, honeypot_script) == old_port
        ]
        if new_port == old_port and old_processes:
            return jsonify({"success": True, "port": new_port})

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("0.0.0.0", new_port))
        except OSError:
            return jsonify({"error": f"Le port {new_port} est déjà utilisé ou indisponible."}), 409

        save_configured_port(new_port)
        try:
            stop_honeypot_processes(old_processes)
            start_honeypot(honeypot_script, port=new_port)
        except (OSError, psutil.Error, RuntimeError) as error:
            save_configured_port(old_port)
            if old_processes:
                try:
                    start_honeypot(honeypot_script, port=old_port)
                except (OSError, RuntimeError) as restart_error:
                    return jsonify({
                        "error": f"Échec du changement de port : {error}. "
                                 f"Le redémarrage sur le port {old_port} a aussi échoué : "
                                 f"{restart_error}"
                    }), 500
            return jsonify({"error": f"Échec du changement de port : {error}"}), 500

    return jsonify({"success": True, "port": new_port})

if __name__ == '__main__':
    print("[*] Démarrage de l'API Flask...")
    app.run(
        host=os.environ.get('HONEYPOT_API_HOST', '127.0.0.1'),
        port=5000,
        debug=False
    )