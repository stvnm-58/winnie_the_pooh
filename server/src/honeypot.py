import socket
import threading
import time
import json
import sys
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import paramiko
from database import init_db, log_attack, update_attack_country, archive_old_data
from fake_shell import handle_fake_shell
from paths import CONFIG_PATH
from utils import get_country_from_ip

HOST_KEY = paramiko.RSAKey.generate(2048)
MAX_CONNECTIONS = 128
MAX_GEOIP_WORKERS = 8
CONNECTION_SLOTS = threading.BoundedSemaphore(MAX_CONNECTIONS)
GEOIP_EXECUTOR = ThreadPoolExecutor(
    max_workers=MAX_GEOIP_WORKERS,
    thread_name_prefix="geoip"
)
SHUTDOWN_EVENT = threading.Event()

class HoneypotServer(paramiko.ServerInterface):
    def __init__(self, client_ip, port):
        # Conserver le contexte de connexion et synchroniser le lancement du shell.
        self.client_ip = client_ip
        self.port = port
        self.event = threading.Event()
        self.shell_lock = threading.Lock()
        self.shell_started = False

    def check_auth_publickey(self, username, key):
        # Refuser les clés publiques : le honeypot capture les essais par mot de passe.
        return paramiko.AUTH_FAILED

    def check_auth_password(self, username, password):
        # Enregistrer l'essai, puis enrichir son pays en arrière-plan.
        attack_id = log_attack(
            self.client_ip, username, password, None, port=self.port
        )
        try:
            future = GEOIP_EXECUTOR.submit(
                resolve_attack_country, attack_id, self.client_ip
            )
            future.add_done_callback(log_country_lookup_error)
        except RuntimeError as error:
            print(f"[-] Géolocalisation non planifiée pour {self.client_ip}: {error}")
        print(
            f"[!] TENTATIVE SSH SUR PORT {self.port} - IP: {self.client_ip} "
            f"| User: {username} | Pass: {password}"
        )
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        # Advertise password authentication as the only supported method.
        return "password"

    def check_channel_request(self, kind, chanid):
        # Allow interactive SSH sessions only.
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        # Démarrer un seul faux shell par connexion, sans bloquer le transport SSH.
        with self.shell_lock:
            if self.shell_started:
                return False
            shell_thread = threading.Thread(
                target=handle_fake_shell,
                args=(channel, self.client_ip, self.port),
                daemon=True
            )
            try:
                shell_thread.start()
            except RuntimeError as error:
                print(f"[-] Impossible de démarrer le faux shell : {error}")
                return False
            self.shell_started = True
            self.event.set()
        return True

    def check_channel_pty_request(self, *args, **kwargs):
        # Accept pseudo-terminal requests for shell clients.
        return True

def handle_connection(client, addr, port):
    # Gérer la négociation et la durée de vie d'une connexion SSH.
    client_ip = addr[0]
    transport = None
    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(HOST_KEY)
        transport.banner_timeout = 15
        transport.auth_timeout = 30
        transport.channel_timeout = 30
        
        sec_opts = transport.get_security_options()
        sec_opts.kex = [k for k in sec_opts.kex if 'curve25519' not in k]
        
        server = HoneypotServer(client_ip, port)
        transport.start_server(server=server)
        
        # Fermer les connexions qui n'ouvrent pas de shell dans les cinq minutes.
        if not server.event.wait(timeout=300):
            return
        
        while transport.is_active():
            time.sleep(1)
            
    except Exception as e:
        print(f"[-] Erreur de transport avec {client_ip} sur port {port}: {e}")
    finally:
        # Libérer le transport et le socket, même après une erreur.
        try:
            if transport:
                transport.close()
        finally:
            client.close()


def _handle_connection_with_slot(client, addr, port):
    # Garantir la libération du créneau même si le traitement SSH échoue.
    try:
        handle_connection(client, addr, port)
    finally:
        CONNECTION_SLOTS.release()


def resolve_attack_country(attack_id, client_ip):
    # Résoudre le pays de l'IP et mettre à jour l'attaque déjà enregistrée.
    country = get_country_from_ip(client_ip)
    update_attack_country(attack_id, country)


def log_country_lookup_error(future):
    # Report asynchronous GeoIP failures without affecting the captured attack.
    error = future.exception()
    if error is not None:
        print(f"[-] Échec de la géolocalisation d'une attaque : {error}")


def archive_periodically():
    # Archiver les données de plus de 30 jours une fois par jour.
    while not SHUTDOWN_EVENT.wait(24 * 60 * 60):
        try:
            archive_old_data(days=30)
        except (sqlite3.Error, OSError) as error:
            print(f"[-] Erreur lors de l'archivage périodique : {error}")

def get_configured_port():
    # Lire et valider le port du listener principal ; utiliser 2222 si la configuration est absente ou invalide.
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if not isinstance(config, dict):
            raise ValueError("La configuration doit être un objet JSON.")
        port = config.get('port', 2222)
        if (
            isinstance(port, int)
            and not isinstance(port, bool)
            and 1 <= port <= 65535
        ):
            return port
        raise ValueError("Le port configuré doit être compris entre 1 et 65535.")
    except FileNotFoundError:
        return 2222
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"[-] Configuration du port invalide ({error}); port 2222 utilisé.")
    return 2222

def main():
    # Initialiser la base et laisser l'instance principale seule responsable de l'archivage.
    init_db()
    is_primary_instance = '--no-archive' not in sys.argv[1:]
    if is_primary_instance:
        archive_old_data(days=30)
        threading.Thread(
            target=archive_periodically,
            name="database-archiver",
            daemon=True
        ).start()
    
    # Utiliser le port fourni en argument, ou celui de config.json à défaut.
    port_argument = next(
        (argument for argument in sys.argv[1:] if argument.isdecimal()),
        None
    )
    if port_argument is not None:
        port = int(port_argument)
        if not 1 <= port <= 65535:
            raise ValueError("Le port doit être compris entre 1 et 65535.")
    else:
        port = get_configured_port()
    
    # Ouvrir le listener SSH sur toutes les interfaces.
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", port))
    server_socket.listen(100)
    
    print(f"[*] Honeypot SSH (Deception Mesh Node) démarré sur le port {port}...")

    try:
        # Accepter les connexions en limitant le nombre de traitements simultanés.
        while True:
            client, addr = server_socket.accept()
            if not CONNECTION_SLOTS.acquire(blocking=False):
                print(f"[-] Trop de connexions actives; rejet de {addr[0]}:{addr[1]}")
                client.close()
                continue

            print(f"[*] Connexion entrante sur le port {port} depuis {addr[0]}:{addr[1]}")
            try:
                threading.Thread(
                    target=_handle_connection_with_slot,
                    args=(client, addr, port),
                    daemon=True
                ).start()
            except RuntimeError as error:
                # Annuler l'acquisition si le thread n'a pas pu démarrer.
                CONNECTION_SLOTS.release()
                client.close()
                print(f"[-] Impossible de créer le thread de connexion : {error}")
    finally:
        # Signaler l'arrêt et fermer le socket d'écoute.
        SHUTDOWN_EVENT.set()
        server_socket.close()

if __name__ == "__main__":
    main()