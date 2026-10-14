from flask import Flask, jsonify, request
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
from database import get_all_attacks, get_all_commands, get_stats

# --- INITIALISATION DE FLASK EN PREMIER ---
app = Flask(__name__)
CORS(app)  # Permet à ton front-end d'interroger l'API sans blocage CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'data', 'config.json')
BAN_STATE_PATH = os.path.join(BASE_DIR, '..', 'data', 'banned_ips.json')
PORT_CHANGE_LOCK = threading.Lock()
BAN_LOCK = threading.Lock()

def get_current_port():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f).get('port', 2222)
        except (OSError, json.JSONDecodeError):
            pass
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

def start_honeypot(honeypot_script):
    process = subprocess.Popen([sys.executable, honeypot_script], cwd=BASE_DIR)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        return process
    raise RuntimeError(
        f"Le processus honeypot s'est arrêté au démarrage (code {process.returncode})."
    )

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
    attacks = get_all_attacks()
    return jsonify(attacks)

@app.route('/api/commands', methods=['GET'])
def api_commands():
    commands = get_all_commands()
    return jsonify(commands)

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
    if isinstance(value, str) and not value.isdecimal():
        return jsonify({"error": "Le port doit être un entier entre 1 et 65535."}), 400

    new_port = int(value)
    if not 1 <= new_port <= 65535:
        return jsonify({"error": "Le port doit être compris entre 1 et 65535."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    with PORT_CHANGE_LOCK:
        old_port = get_current_port()
        old_processes = find_honeypot_processes(honeypot_script)
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
            start_honeypot(honeypot_script)
        except (OSError, psutil.Error, RuntimeError) as error:
            save_configured_port(old_port)
            if old_processes:
                try:
                    start_honeypot(honeypot_script)
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
    app.run(host='0.0.0.0', port=5000, debug=True)