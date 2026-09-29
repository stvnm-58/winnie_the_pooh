from flask import Flask, jsonify
from flask_cors import CORS
from database import get_all_attacks

app = Flask(__name__)
CORS(app)  # Permet à ton futur client React d'interroger l'API sans blocage CORS

@app.route('/api/attacks', methods=['GET'])
def api_attacks():
    attacks = get_all_attacks()
    # Ici, plus tard, on ajoutera la logique pour enrichir avec le Pays
    return jsonify(attacks)

if __name__ == '__main__':
    app.run(debug=True, port=5000)