import socket
import threading
import time
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
        log_attack(self.client_ip, username, password, country)
        return paramiko.AUTH_SUCCESSFUL

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        self.event.set()
        # On transmet l'IP du client ici au faux shell
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

def main():
    init_db()
    
    # Exécute l'archivage automatique des données de plus de 30 jours au démarrage du honeypot
    archive_old_data(days=30)
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", 2222))
    server_socket.listen(100)
    
    print("[*] Honeypot SSH (Faux Shell) démarré sur le port 2222...")

    while True:
        client, addr = server_socket.accept()
        print(f"[*] Connexion entrante depuis {addr[0]}:{addr[1]}")
        threading.Thread(target=handle_connection, args=(client, addr)).start()

if __name__ == "__main__":
    main()