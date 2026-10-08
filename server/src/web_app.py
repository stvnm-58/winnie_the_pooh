from flask import Flask, jsonify
from flask_cors import CORS
import os
import psutil
from database import get_all_attacks, get_all_commands, get_stats

app = Flask(__name__)
CORS(app)  # Permet à ton front-end d'interroger l'API sans blocage CORS

@app.route('/api/attacks', methods=['GET'])
def api_attacks():
    """Route pour récupérer l'historique des connexions/attaques."""
    attacks = get_all_attacks()
    return jsonify(attacks)

@app.route('/api/commands', methods=['GET'])
def api_commands():
    """Route pour récupérer toutes les commandes du faux shell."""
    commands = get_all_commands()
    return jsonify(commands)

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Route pour récupérer les statistiques globales du dashboard."""
    stats = get_stats()
    return jsonify(stats)

@app.route('/api/status', methods=['GET'])
def api_status():
    """Route pour vérifier si le honeypot est actif via la présence du processus."""
    active = False
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and any('honeypot.py' in part for part in cmdline):
                active = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    return jsonify({"active": active})

if __name__ == '__main__':
    print("[*] Démarrage de l'API Flask...")
    app.run(host='0.0.0.0', port=5000, debug=True)