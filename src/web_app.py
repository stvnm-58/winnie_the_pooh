from flask import Flask, jsonify, render_template
from database import get_all_attacks

app = Flask(__name__, template_folder='../templates', static_folder='../static')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/attacks')
def api_attacks():
    attacks = get_all_attacks()
    # Ici, plus tard, on ajoutera la logique pour enrichir avec le Pays
    return jsonify(attacks)

if __name__ == '__main__':
    app.run(debug=True, port=5000)