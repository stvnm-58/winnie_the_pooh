import socket
import threading
import time
import json
import os
import paramiko
from database import init_db, log_attack, archive_old_data
from fake_shell import handle_fake_shell
from utils import get_country_from_ip

HOST_KEY = paramiko.RSAKey.generate(2048)

class HoneypotServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.client_ip = client_ip
        self.event = threading.Event()

    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_FAILED

    def check_auth_password(self, username, password):
        country = get_country_from_ip(self.client_ip)
        print(f"[!] CONNEXION ACCEPTÉE (Faux Shell) - IP: {self.client_ip} | User: {username} | Pass: {password} | Country: {country}")
        
        # Enregistrement de l'attaque dans la base de données
        log_attack(self.client_ip, username, password, country)
        
        # Le honeypot accepte l'authentification (passoire volontaire) 
        # Le bannissement se fera manuellement à la demande via le dashboard
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        self.event.set()
        threading.Thread(target=handle_fake_shell, args=(channel, self.client_ip)).start()
        return True

    def check_channel_pty_request(self, *args, **kwargs):
        return True

def handle_connection(client, addr):
    client_ip = addr[0]
    transport = None
    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(HOST_KEY)
        
        sec_opts = transport.get_security_options()
        sec_opts.kex = [k for k in sec_opts.kex if 'curve25519' not in k]
        
        server = HoneypotServer(client_ip)
        transport.start_server(server=server)
        
        server.event.wait(timeout=300)
        
        while transport.is_active():
            time.sleep(1)
            
    except Exception as e:
        print(f"[-] Erreur de transport avec {client_ip}: {e}")
    finally:
        if transport:
            try:
                transport.close()
            except:
                pass

def get_configured_port():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, 'data', 'config.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                port = json.load(f).get('port', 2222)
            if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
                return port
            raise ValueError(f"Port invalide dans la configuration : {port!r}")
    except OSError as error:
        raise OSError(f"Impossible de lire la configuration du honeypot : {error}") from error
    return 2222

def main():
    init_db()
    archive_old_data(days=30)
    
    port = get_configured_port()
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", port))
    server_socket.listen(100)
    
    print(f"[*] Honeypot SSH (Manual Active Defense) démarré sur le port {port}...")

    while True:
        client, addr = server_socket.accept()
        print(f"[*] Connexion entrante depuis {addr[0]}:{addr[1]}")
        threading.Thread(target=handle_connection, args=(client, addr)).start()

if __name__ == "__main__":
    main()