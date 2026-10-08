from flask import Flask, jsonify
from flask_cors import CORS
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

if __name__ == '__main__':
    print("[*] Démarrage de l'API Flask...")
    app.run(debug=True, port=5000)