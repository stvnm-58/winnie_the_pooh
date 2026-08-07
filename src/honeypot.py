import socket
import threading
import paramiko
import os
from database import init_db, log_attack

# Génération d'une fausse clé RSA pour le serveur
HOST_KEY = paramiko.RSAKey.generate(2048)

class HoneypotServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.client_ip = client_ip
        self.event = threading.Event()

    def check_auth_password(self, username, password):
        print(f"[!] Tentative SSH - IP: {self.client_ip} | User: {username} | Pass: {password}")
        # Enregistrement en base de données
        log_attack(self.client_ip, username, password)
        # On refuse l'authentification pour leurrer l'attaquant
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password"

def handle_connection(client, addr):
    client_ip = addr[0]
    transport = paramiko.Transport(client)
    transport.add_server_key(HOST_KEY)
    server = HoneypotServer(client_ip)
    
    try:
        transport.start_server(server=server)
    except Exception as e:
        print(f"[-] Erreur de transport avec {client_ip}: {e}")
    finally:
        try:
            transport.close()
        except:
            pass

def main():
    init_db()
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("0.0.0.0", 2222))
    server_socket.listen(100)
    
    print("[*] Honeypot SSH démarré et à l'écoute sur le port 2222...")

    while True:
        client, addr = server_socket.accept()
        print(f"[*] Connexion entrante depuis {addr[0]}:{addr[1]}")
        threading.Thread(target=handle_connection, args=(client, addr)).start()

if __name__ == "__main__":
    main()