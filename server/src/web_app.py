import jwt
import datetime
import random
import time
from collections import defaultdict
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
import smtplib
import sqlite3
import ssl
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import check_password_hash, generate_password_hash
from database import (
    get_all_attacks,
    get_all_commands,
    get_country_updates,
    get_latest_country_update_id,
    get_stats,
    create_password_reset_token,
    consume_password_reset_token
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
PASSWORD_RESET_LOCK = threading.Lock()

CORS(
    app,
    resources={r'/api/*': {'origins': ALLOWED_ORIGINS}},
    supports_credentials=True,
    allow_headers=['Content-Type'],
    methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
)

PUBLIC_API_ENDPOINTS = {
    'auth_status',
    'setup_authentication',
    'login',
    'forgot_password',
    'reset_password'
}


def load_auth_file():
    """Lit le fichier JSON qui contient le compte administrateur et ses paramètres associés.

    Un fichier absent est traité comme une configuration encore inexistante et renvoie
    un dictionnaire vide. Les erreurs d'accès et les erreurs JSON sont converties en
    RuntimeError afin que les routes puissent renvoyer une erreur explicite. Le
    contenu racine doit être un objet JSON, pas une liste ou une valeur scalaire.
    """
    # L'absence du fichier signifie « pas encore configuré » ; les autres problèmes de lecture sont des erreurs.
    try:
        with open(AUTH_CONFIG_PATH, 'r', encoding='utf-8') as auth_file:
            configuration = json.load(auth_file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError('Configuration du compte indisponible.') from error
    if not isinstance(configuration, dict):
        raise RuntimeError('Configuration du compte invalide.')
    return configuration


def save_auth_file(configuration):
    """Enregistre la configuration d'authentification sans exposer un fichier partiel.

    Le fichier temporaire est créé dans le même dossier que la destination pour
    permettre un remplacement atomique. Ses permissions sont restreintes avant
    os.replace ; le bloc finally tente de supprimer le temporaire en cas d'échec.
    Les erreurs d'écriture sont remontées comme RuntimeError aux routes appelantes.
    """
    # Le temporaire reste dans le répertoire cible afin que os.replace soit atomique sur le même système de fichiers.
    auth_dir = os.path.dirname(AUTH_CONFIG_PATH)
    temporary_path = None
    try:
        os.makedirs(auth_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=auth_dir,
            delete=False
        ) as auth_file:
            # Conserver le chemin permet de nettoyer le fichier si l'écriture ou le remplacement échoue.
            temporary_path = auth_file.name
            json.dump(configuration, auth_file)
        # Restreindre les permissions avant de publier la configuration, qui contient des secrets.
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, AUTH_CONFIG_PATH)
    except OSError as error:
        raise RuntimeError('Impossible d’enregistrer la configuration du compte.') from error
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError as error:
                app.logger.warning('Impossible de supprimer un fichier temporaire: %s', error)


def is_valid_email(email):
    """Applique les contrôles de format simples utilisés pour les adresses de récupération.

    La fonction vérifie le type, la longueur maximale, la présence d'une partie
    locale et d'un domaine séparés par @, un point dans le domaine, et l'absence
    d'espaces. Elle ne prétend pas valider toutes les règles de la norme e-mail.
    """
    # Cette validation est volontairement pragmatique : elle filtre les entrées manifestement invalides.
    if not isinstance(email, str) or len(email) > 254:
        return False
    # Séparer à la première arobase, puis contrôler la présence des deux parties.
    local_part, separator, domain = email.partition('@')
    return bool(
        separator
        and local_part
        and domain
        and '.' in domain
        and not any(character.isspace() for character in email)
    )


def auth_configuration_is_valid():
    """Indique si les identifiants et le secret JWT sont disponibles et valides.

    La validation effective est centralisée dans get_auth_configuration ; cette
    fonction ne fait que convertir son résultat en booléen pour les routes de setup.
    """
    # Un seul point de validation évite de dupliquer les règles du fichier et des variables d'environnement.
    return bool(get_auth_configuration())


def get_auth_configuration():
    """Charge et valide la configuration utilisée pour authentifier l'administrateur.

    Les variables d'environnement sont prioritaires uniquement si les trois valeurs
    JWT, username et hash de mot de passe sont présentes ensemble. Sinon, le fichier
    auth.json est lu et doit contenir un secret d'au moins 32 octets, un username
    non vide et un hash non vide. En cas d'absence, de JSON invalide ou de valeurs
    incomplètes, la fonction journalise les erreurs de lecture et renvoie None.

    Returns:
        Un tuple (secret JWT, nom administrateur, hash du mot de passe), ou None.
    """
    # N'utiliser la configuration d'environnement que si elle est entièrement fournie.
    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return JWT_SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD_HASH

    # Sinon, charger la configuration persistée ; les erreurs sont journalisées plutôt que propagées.
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

    # Extraire les champs requis puis valider leurs types et la force minimale du secret de signature.
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
    """Applique les contrôles communs avant le traitement de chaque requête API.

    Les chemins hors API et les requêtes CORS preflight OPTIONS passent sans
    authentification. Le rapport d'essai automatique est également exempté.
    Les autres appels sont contrôlés par origine (les écritures exigent une
    origine autorisée), puis les endpoints publics sont laissés passer. Enfin,
    les endpoints protégés exigent une configuration valide et un cookie JWT
    winnie_token signé avec HS256 ; le claim user est placé dans flask.g.

    Returns:
        None si la requête peut continuer, ou une réponse JSON d'erreur HTTP.
    """
    # Laisser passer les routes hors API et les preflights CORS, qui ne portent pas les identifiants de session.
    if not request.path.startswith('/api/') or request.method == 'OPTIONS':
        return None

    # Ce point d'entrée de signalement est volontairement public pour le mécanisme de suivi automatique.
    if request.path == '/api/report-attempt':
        return None

    # Refuser une origine non autorisée ; toutes les requêtes mutantes doivent fournir une origine autorisée.
    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') not in ALLOWED_ORIGINS:
        return jsonify({'error': 'Origine non autorisée'}), 403
    if request.method not in ('GET', 'HEAD') and origin not in ALLOWED_ORIGINS:
        return jsonify({'error': 'Origine requise ou non autorisée'}), 403

    # Les endpoints publics servent notamment au setup initial, à la connexion et à la récupération.
    if request.endpoint in PUBLIC_API_ENDPOINTS:
        return None

    # Les autres routes nécessitent une configuration et un cookie JWT valide.
    auth_configuration = get_auth_configuration()
    if not auth_configuration:
        return jsonify({'error': 'Authentification non configurée sur le serveur'}), 503
    secret, _, _ = auth_configuration

    token = request.cookies.get('winnie_token')
    if not token:
        return jsonify({'error': 'Jeton d’authentification manquant'}), 401

    try:
        # Vérifier la signature/expiration puis exposer l'identité aux routes via le contexte Flask.
        claims = jwt.decode(token, secret, algorithms=['HS256'])
        if not isinstance(claims.get('user'), str) or not claims['user']:
            raise jwt.InvalidTokenError('User claim is missing')
        g.current_user = claims['user']
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Session expirée, veuillez vous reconnecter'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Jeton invalide'}), 401

    return None


# Endpoint public : GET /api/auth-status ne requiert ni corps JSON ni session.
# Informe le frontend si le setup initial est requis ; renvoie aussi HTTP 503
# lorsqu'un fichier de compte existe mais ne peut pas être utilisé.
@app.route('/api/auth-status', methods=['GET'])
def auth_status():
    """Expose à l'interface l'état de configuration du compte administrateur.

    Renvoie setup_required=False si les identifiants peuvent être chargés. Si un
    fichier auth.json existe mais n'est pas valide, renvoie HTTP 503 plutôt que de
    proposer une nouvelle inscription. Si le fichier n'existe pas, le setup est requis.
    """
    # Distinguer une première installation d'un fichier présent mais inutilisable.
    if auth_configuration_is_valid():
        return jsonify({'setup_required': False})
    if os.path.exists(AUTH_CONFIG_PATH):
        return jsonify({
            'error': 'Le fichier de configuration du compte administrateur est invalide'
        }), 503
    return jsonify({'setup_required': True})


def create_session_response(username, secret, status=200):
    """Construit la réponse de connexion et installe le cookie de session JWT.

    Le JWT contient le nom d'utilisateur et une expiration basée sur la durée
    globale SESSION_TTL_SECONDS. Le cookie est HttpOnly, SameSite=Lax, limité au
    chemin /api et marqué Secure si la requête est HTTPS ou si le réglage
    HONEYPOT_COOKIE_SECURE l'impose.

    Args:
        username: Nom de l'administrateur authentifié.
        secret: Clé secrète utilisée pour signer le JWT en HS256.
        status: Code HTTP à placer dans la réponse (201 lors du premier setup).
    """
    # Signer une identité et une date d'expiration avec le secret courant du compte.
    token = jwt.encode({
        'user': username,
        'exp': datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=SESSION_TTL_SECONDS)
    }, secret, algorithm='HS256')
    # Le cookie HttpOnly limite l'accès JavaScript ; Secure dépend de HTTPS ou du réglage explicite.
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


# Endpoint public, à usage unique : POST /api/setup reçoit username, password
# et éventuellement email dans un objet JSON. Crée le compte administrateur,
# puis renvoie HTTP 201 et ouvre une session ; entrées invalides : HTTP 400,
# compte déjà présent/concurrent : HTTP 409, échec de configuration : HTTP 5xx.
@app.route('/api/setup', methods=['POST'])
def setup_authentication():
    """Valide et crée le compte administrateur initial, puis ouvre sa première session.

    L'endpoint refuse toute nouvelle inscription après la configuration du compte.
    Il valide username, mot de passe (12 à 1024 caractères), e-mail facultatif et
    présence d'une origine CORS. Il génère ensuite un secret JWT et un hash Werkzeug,
    crée auth.json exclusivement (O_EXCL) avec des permissions restreintes, puis
    renvoie un cookie de session avec HTTP 201. Les erreurs de validation, de
    concurrence et d'écriture sont renvoyées avec des statuts explicites.
    """
    # Le setup est à usage unique ; vérifier l'état avant même de lire les données envoyées.
    if auth_configuration_is_valid():
        return jsonify({'error': 'Le compte administrateur est déjà configuré'}), 409

    # Valider et normaliser les champs avant de générer ou écrire des secrets.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps de requête invalide'}), 400
    username = data.get('username')
    password = data.get('password')
    admin_email = data.get('email', '')
    if not isinstance(username, str) or not username.strip() or len(username.strip()) > 64:
        return jsonify({'error': 'Identifiant requis (64 caractères maximum)'}), 400
    if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
        return jsonify({'error': 'Le mot de passe doit contenir entre 12 et 1024 caractères'}), 400
    if admin_email and not is_valid_email(admin_email.strip()):
        return jsonify({'error': 'Adresse e-mail de récupération invalide'}), 400
    if len(ALLOWED_ORIGINS) == 0:
        return jsonify({'error': 'Aucune origine autorisée n’est configurée'}), 503

    # Le hash est persisté à la place du mot de passe ; le secret JWT est indépendant et aléatoire.
    configuration = {
        'jwt_secret': secrets.token_urlsafe(48),
        'admin_username': username.strip(),
        'admin_password_hash': generate_password_hash(password)
    }
    if admin_email:
        configuration['admin_email'] = admin_email.strip().lower()
    # O_EXCL empêche deux requêtes simultanées de remplacer chacune le compte initial de l'autre.
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

    # Écrire le JSON créé exclusivement, puis appliquer les permissions du fichier de compte.
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

    # La création du compte ouvre une session immédiatement, comme une connexion réussie.
    return create_session_response(
        configuration['admin_username'],
        configuration['jwt_secret'],
        status=201
    )


# Endpoint protégé : GET /api/account renvoie l'adresse de récupération et les
# paramètres SMTP non secrets. PATCH attend email et les champs SMTP à modifier ;
# le mot de passe SMTP n'est jamais renvoyé. Validation : HTTP 400, configuration
# ou stockage indisponible : HTTP 503/500.
@app.route('/api/account', methods=['GET', 'PATCH'])
def account_settings():
    """Expose ou modifie l'adresse de récupération et les paramètres SMTP du compte.

    GET assemble les valeurs stockées dans auth.json et les éventuelles variables
    d'environnement, sans renvoyer le mot de passe SMTP lui-même. PATCH n'est
    disponible que pour un compte géré dans le fichier : il valide l'e-mail, l'hôte,
    le port et les champs SMTP, conserve le mot de passe existant si aucun nouveau
    n'est fourni, puis sauvegarde les paramètres. Les secrets fournis par
    l'environnement doivent être modifiés dans leur gestionnaire externe.
    """
    # Une configuration illisible interdit aussi bien l'affichage que la modification des réglages.
    try:
        configuration = load_auth_file()
    except RuntimeError as error:
        return jsonify({'error': str(error)}), 503

    if request.method == 'GET':
        # Les variables d'environnement priment pour SMTP ; ne renvoyer que l'indicateur de présence du secret.
        recovery_email = configuration.get(
            'admin_email',
            os.environ.get('HONEYPOT_ADMIN_EMAIL', '')
        )
        smtp_user = os.environ.get('HONEYPOT_SMTP_USERNAME') or configuration.get('smtp_user', '')
        smtp_from = os.environ.get('HONEYPOT_SMTP_FROM') or configuration.get('smtp_from', smtp_user)
        smtp_host = os.environ.get('HONEYPOT_SMTP_HOST') or configuration.get('smtp_host', '')
        smtp_port = os.environ.get('HONEYPOT_SMTP_PORT') or configuration.get('smtp_port', 587)
        return jsonify({
            'email': recovery_email if isinstance(recovery_email, str) else '',
            'smtp_host': smtp_host if isinstance(smtp_host, str) else '',
            'smtp_port': str(smtp_port),
            'smtp_user': smtp_user if isinstance(smtp_user, str) else '',
            'smtp_from': smtp_from if isinstance(smtp_from, str) else '',
            'smtp_password_configured': bool(
                os.environ.get('HONEYPOT_SMTP_PASSWORD')
                or configuration.get('smtp_password')
            )
        })

    # Un compte défini par environnement doit être modifié dans son gestionnaire de secrets, pas dans auth.json.
    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return jsonify({
            'error': 'Configurez l’adresse de récupération avec HONEYPOT_ADMIN_EMAIL dans l’environnement du serveur.'
        }), 503

    # Le courriel de récupération est requis et normalisé avant toute modification de configuration.
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('email'), str):
        return jsonify({'error': 'Adresse e-mail requise'}), 400
    email = data['email'].strip().lower()
    if not is_valid_email(email):
        return jsonify({'error': 'Adresse e-mail de récupération invalide'}), 400
    configuration['admin_email'] = email

    # Préserver les valeurs omises, puis valider les champs SMTP avant d'enregistrer quoi que ce soit.
    smtp_host = data.get('smtp_host', configuration.get('smtp_host', ''))
    smtp_port = data.get('smtp_port', configuration.get('smtp_port', 587))
    smtp_user = data.get('smtp_user', configuration.get('smtp_user', ''))
    smtp_from = data.get('smtp_from', configuration.get('smtp_from', smtp_user))
    smtp_password = data.get('smtp_password', '')

    if not all(isinstance(value, str) for value in (smtp_host, smtp_user, smtp_from)):
        return jsonify({'error': 'Configuration SMTP invalide.'}), 400
    smtp_host = smtp_host.strip()
    smtp_user = smtp_user.strip()
    smtp_from = smtp_from.strip().lower()
    if smtp_host and (len(smtp_host) > 253 or any(char.isspace() for char in smtp_host)):
        return jsonify({'error': 'Nom de serveur SMTP invalide.'}), 400
    try:
        smtp_port = int(smtp_port)
    except (TypeError, ValueError):
        return jsonify({'error': 'Le port SMTP doit être compris entre 1 et 65535.'}), 400
    if not 1 <= smtp_port <= 65535:
        return jsonify({'error': 'Le port SMTP doit être compris entre 1 et 65535.'}), 400
    if smtp_from and not is_valid_email(smtp_from):
        return jsonify({'error': 'Adresse d’expéditeur SMTP invalide.'}), 400
    if not isinstance(smtp_password, str) or len(smtp_password) > 1024:
        return jsonify({'error': 'Mot de passe SMTP invalide.'}), 400
    # Un secret SMTP vide signifie « conserver l'existant » ; les autres champs vides suppriment la clé.
    if smtp_password:
        configuration['smtp_password'] = smtp_password
    if smtp_host:
        configuration['smtp_host'] = smtp_host
    else:
        configuration.pop('smtp_host', None)
    if smtp_user:
        configuration['smtp_user'] = smtp_user
    else:
        configuration.pop('smtp_user', None)
    if smtp_from:
        configuration['smtp_from'] = smtp_from
    else:
        configuration.pop('smtp_from', None)
    configuration['smtp_port'] = smtp_port

    # Sauvegarder la nouvelle configuration, puis renvoyer les paramètres non secrets à l'interface.
    try:
        save_auth_file(configuration)
    except RuntimeError as error:
        app.logger.error('Impossible de mettre à jour l’adresse de récupération: %s', error)
        return jsonify({'error': str(error)}), 500
    return jsonify({
        'success': True,
        'email': email,
        'smtp_host': configuration.get('smtp_host', ''),
        'smtp_port': str(configuration.get('smtp_port', 587)),
        'smtp_user': configuration.get('smtp_user', ''),
        'smtp_from': configuration.get('smtp_from', ''),
        'smtp_password_configured': bool(configuration.get('smtp_password'))
    })


# Endpoint public : POST /api/login attend username et password dans un JSON.
# Retourne le username et un cookie de session HttpOnly si les identifiants sont
# valides ; corps invalide : HTTP 400, identifiants erronés : HTTP 401,
# configuration d'authentification absente/invalide : HTTP 503.
@app.route('/api/login', methods=['POST'])
def login():
    """Authentifie l'administrateur à partir du JSON reçu et ouvre une session.

    Vérifie d'abord que le corps contient des chaînes username/password non vides,
    puis charge la configuration et compare le nom et le mot de passe au hash
    Werkzeug. Une configuration absente ou un hash invalide produit une erreur
    serveur ; des identifiants incorrects renvoient HTTP 401. En cas de succès,
    create_session_response émet le JWT HttpOnly.
    """
    # Vérifier le format du corps et la présence de deux chaînes non vides.
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

    # Charger le couple de compte attendu ; une configuration absente est une panne serveur, pas un mauvais mot de passe.
    auth_configuration = get_auth_configuration()
    if not auth_configuration:
        return jsonify({'error': 'Authentification non configurée sur le serveur'}), 503
    secret, admin_username, password_hash = auth_configuration

    # Comparer d'abord le nom, puis faire vérifier le mot de passe par Werkzeug contre le hash stocké.
    try:
        password_matches = username == admin_username and check_password_hash(
            password_hash,
            password
        )
    except (TypeError, ValueError) as error:
        app.logger.error('Le hash de mot de passe administrateur est invalide: %s', error)
        return jsonify({'error': 'Configuration du mot de passe invalide'}), 503

    # Seul un couple valide reçoit une session ; les identifiants erronés restent une réponse 401 générique.
    if password_matches:
        return create_session_response(username, secret)

    return jsonify({'error': 'Identifiants incorrects'}), 401


# Endpoint protégé : GET /api/session renvoie l'identité associée au cookie JWT.
# Le middleware protect_api valide la session avant l'exécution du handler.
@app.route('/api/session', methods=['GET'])
def get_session():
    """Renvoie l'identité de la session courante, déjà vérifiée par protect_api.

    Le filtre global a validé le JWT et placé son claim user dans flask.g avant
    l'appel de cette route.
    """
    # Le before_request a déjà authentifié la requête et renseigné cette valeur.
    return jsonify({'username': g.current_user})


# Endpoint protégé : POST /api/logout supprime le cookie de session du navigateur.
# Le JWT n'étant pas conservé côté serveur, cette route n'ajoute pas de révocation
# serveur ; les autres requêtes échouent dès que le cookie client est supprimé.
@app.route('/api/logout', methods=['POST'])
def logout():
    """Demande au navigateur de supprimer son cookie d'authentification.

    La réponse utilise les mêmes attributs de chemin et de sécurité que le cookie
    de session. Le JWT n'est pas stocké côté serveur : la déconnexion consiste donc
    à effacer le cookie client.
    """
    # Effacer le cookie avec les mêmes attributs de portée que lors de sa création.
    response = jsonify({'success': True})
    response.delete_cookie(
        'winnie_token',
        path='/api',
        secure=request.is_secure or COOKIE_SECURE,
        httponly=True,
        samesite='Lax'
    )
    return response


# --- ROUTES DE RÉINITIALISATION DE MOT DE PASSE ---

# Endpoint public : POST /api/auth/forgot-password attend {"username": "..."}.
# Envoie un lien de récupération valable 15 minutes si le compte et SMTP sont
# configurés ; pour un compte inconnu, la réponse reste générique afin de ne pas
# révéler son existence. Corps invalide : HTTP 400, SMTP/configuration : HTTP 5xx.
@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    """Envoie par SMTP un lien à usage unique pour réinitialiser le mot de passe.

    Valide le username, refuse les comptes gérés entièrement par variables
    d'environnement, puis charge l'e-mail de récupération et les paramètres SMTP.
    Pour éviter de révéler l'existence du compte, un username inconnu ou sans
    adresse valide reçoit la même réponse générique de succès que la demande
    normale. Pour le compte connu, crée en base un jeton aléatoire valable 15
    minutes, construit un lien sur l'origine de la requête et envoie le message via
    SMTP_SSL sur le port 465 ou SMTP avec STARTTLS sur les autres ports.
    Les erreurs d'envoi ou de stockage sont journalisées et renvoyées au client.
    """
    # Vérifier le type et la taille de l'identifiant avant de toucher aux données du compte.
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('username'), str):
        return jsonify({'error': 'Identifiant invalide'}), 400
    username = data['username'].strip()
    if not username or len(username) > 64:
        return jsonify({'error': 'Identifiant invalide'}), 400

    # Charger les réglages nécessaires ; la récupération par mail n'est pas prise en charge pour les comptes d'environnement.
    try:
        auth_config = load_auth_file()
    except RuntimeError as error:
        app.logger.error('Impossible de lire la configuration du compte: %s', error)
        return jsonify({'error': 'Authentification non configurée'}), 503

    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return jsonify({
            'error': 'La récupération par e-mail n’est pas disponible lorsque l’authentification est fournie par variables d’environnement.'
        }), 503
    auth_configuration = get_auth_configuration()
    if not auth_configuration:
        return jsonify({'error': 'Authentification non configurée'}), 503
    _, admin_username, _ = auth_configuration
    admin_email = auth_config.get(
        'admin_email',
        os.environ.get('HONEYPOT_ADMIN_EMAIL', '')
    )

    # Un identifiant inconnu suit le même chemin de réponse que le succès afin de ne pas révéler l'existence du compte.
    if username != admin_username or not is_valid_email(admin_email):
        return jsonify({
            'success': True,
            'message': 'Si un compte est associé à cet identifiant, un lien de réinitialisation a été envoyé.'
        })

    # Résoudre chaque réglage SMTP depuis l'environnement puis le fichier, et vérifier les valeurs nécessaires.
    smtp_host = os.environ.get('HONEYPOT_SMTP_HOST') or auth_config.get('smtp_host', '')
    smtp_user = os.environ.get('HONEYPOT_SMTP_USERNAME') or auth_config.get('smtp_user', '')
    smtp_password = os.environ.get('HONEYPOT_SMTP_PASSWORD') or auth_config.get('smtp_password', '')
    smtp_from = os.environ.get('HONEYPOT_SMTP_FROM') or auth_config.get('smtp_from', smtp_user)
    smtp_port_value = os.environ.get('HONEYPOT_SMTP_PORT') or auth_config.get('smtp_port', 587)

    if not is_valid_email(admin_email):
        admin_email = ''
    try:
        smtp_port = int(smtp_port_value)
        if not 1 <= smtp_port <= 65535:
            raise ValueError('Port SMTP hors plage.')
    except (TypeError, ValueError):
        return jsonify({'error': 'Configuration SMTP invalide.'}), 503
    if not all(
        isinstance(value, str) and value
        for value in (smtp_host, smtp_user, smtp_password, smtp_from)
    ):
        return jsonify({'error': 'Le service e-mail de récupération n’est pas configuré.'}), 503

    # Persister un jeton court avant de construire le lien et le message envoyé au destinataire enregistré.
    origin = request.headers.get('Origin', '').rstrip('/')
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15)
    ).strftime('%Y-%m-%d %H:%M:%S')
    try:
        create_password_reset_token(admin_username, token, expires_at)
        reset_link = f'{origin}/?token={quote(token)}'
        message = MIMEMultipart()
        message['From'] = smtp_from
        message['To'] = admin_email
        message['Subject'] = 'Réinitialisation de votre mot de passe - Honeypot Swarm'
        message.attach(MIMEText(
            'Bonjour,\n\n'
            f'Voici votre lien de réinitialisation (valable 15 minutes) :\n{reset_link}\n\n'
            'Si vous n’êtes pas à l’origine de cette demande, ignorez ce message.',
            'plain'
        ))

        # Choisir TLS implicite pour le port 465 ; les autres ports utilisent STARTTLS avant l'authentification.
        if smtp_port == 465:
            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                timeout=10,
                context=ssl.create_default_context()
            ) as mail_server:
                mail_server.login(smtp_user, smtp_password)
                mail_server.sendmail(smtp_from, admin_email, message.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as mail_server:
                mail_server.starttls(context=ssl.create_default_context())
                mail_server.login(smtp_user, smtp_password)
                mail_server.sendmail(smtp_from, admin_email, message.as_string())
    except (OSError, RuntimeError, sqlite3.Error, smtplib.SMTPException) as error:
        app.logger.error('Échec de l’envoi de l’e-mail de récupération: %s', error)
        return jsonify({'error': 'Impossible d’envoyer le lien de récupération.'}), 502

    # Ne confirmer l'envoi que lorsque la transmission SMTP s'est terminée sans exception.
    return jsonify({
        'success': True,
        'message': 'Si un compte est associé à cet identifiant, un lien de réinitialisation a été envoyé.'
    })


# Endpoint public : POST /api/auth/reset-password attend token et password.
# Consomme un jeton valide, change le hash du mot de passe et renouvelle la clé
# JWT. Jeton/mot de passe invalide : HTTP 400 ; erreur SQLite : HTTP 500 ;
# récupération non prise en charge avec identifiants d'environnement : HTTP 503.
@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    """Valide le jeton de récupération et remplace les secrets d'authentification.

    Vérifie le format du jeton et la longueur du nouveau mot de passe, puis refuse
    le flux si les identifiants proviennent de variables d'environnement. Le verrou
    empêche deux demandes concurrentes de consommer le même jeton. Après validation
    atomique du jeton en base, le username doit correspondre au compte de auth.json ;
    le mot de passe est hashé et le secret JWT renouvelé, ce qui invalide les
    sessions signées avec l'ancien secret.
    """
    # Valider la forme des données et la politique de longueur avant de consommer le jeton.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps de requête invalide'}), 400

    token = data.get('token')
    new_password = data.get('password')

    if (
        not isinstance(token, str)
        or not token
        or len(token) > 256
        or not isinstance(new_password, str)
        or not 12 <= len(new_password) <= 1024
    ):
        return jsonify({'error': 'Token invalide ou mot de passe trop court (12 caractères min)'}), 400

    # Le changement ne peut pas être écrit dans le magasin immuable des variables d'environnement.
    if JWT_SECRET_KEY and ADMIN_USERNAME and ADMIN_PASSWORD_HASH:
        return jsonify({
            'error': 'La réinitialisation par e-mail n’est pas disponible lorsque l’authentification est fournie par variables d’environnement.'
        }), 503

    # Sérialiser la consommation du jeton afin qu'une seule requête puisse réussir ce reset.
    with PASSWORD_RESET_LOCK:
        # Après validation et consommation du jeton, vérifier qu'il vise toujours l'administrateur configuré.
        try:
            reset_username = consume_password_reset_token(token)
        except sqlite3.Error as error:
            app.logger.error('Impossible de valider le jeton de récupération: %s', error)
            return jsonify({'error': 'Impossible de valider le lien de récupération.'}), 500
        if not reset_username:
            return jsonify({'error': 'Le lien de réinitialisation est invalide ou a expiré.'}), 400
        try:
            config = load_auth_file()
            if config.get('admin_username') != reset_username:
                return jsonify({'error': 'Le lien de réinitialisation est invalide ou a expiré.'}), 400
            # Changer aussi la clé JWT invalide les cookies des sessions déjà ouvertes.
            config['admin_password_hash'] = generate_password_hash(new_password)
            config['jwt_secret'] = secrets.token_urlsafe(48)
            save_auth_file(config)
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
            app.logger.error('Erreur lors de la mise à jour du mot de passe: %s', error)
            return jsonify({'error': 'Impossible de mettre à jour le mot de passe.'}), 500

    return jsonify({'success': True, 'message': 'Mot de passe réinitialisé avec succès.'})


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT_CHANGE_LOCK = threading.Lock()
BAN_LOCK = threading.Lock()
HONEYPOT_LOCK = threading.Lock()
MAX_API_PAGE_SIZE = 500

# --- STRUCTURES POUR L'AUTO-BAN (RATE LIMITING & STATS) ---
ATTEMPT_HISTORY = defaultdict(list)
AUTO_BAN_STATS = {} 
AUTO_BAN_ENABLED = True
RATE_LIMIT_WINDOW = 15     
RATE_LIMIT_MAX_ATTEMPTS = 15 

def get_current_port():
    """Lit le port de l'instance principale depuis le fichier de configuration.

    L'absence du fichier signifie que la configuration par défaut (2222) s'applique.
    Une erreur de lecture ou un JSON invalide est signalé sur stdout avant de
    retourner ce même port par défaut. Une valeur n'est acceptée que si le JSON est
    un objet et si port est un entier Python (pas un booléen) compris entre 1 et
    65535.

    Returns:
        Le port configuré ou le port par défaut 2222.
    """
    # Lire la configuration sans faire échouer le démarrage si le fichier n'a pas encore été créé.
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        return 2222
    except (OSError, json.JSONDecodeError) as error:
        print(f"[-] Impossible de lire la configuration du port ({error}); port 2222 utilisé.")
        return 2222

    # Refuser bool (sous-classe de int en Python) et valeurs hors plage TCP/UDP.
    if isinstance(config, dict):
        port = config.get('port', 2222)
        if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
            return port
    print("[-] Configuration du port invalide; port 2222 utilisé.")
    return 2222

def save_configured_port(port):
    """Écrit le nouveau port principal dans config.json.

    Crée le dossier de données s'il n'existe pas, sérialise {"port": port} dans un
    fichier temporaire placé dans le même dossier, puis remplace la configuration
    par os.replace. Le bloc finally nettoie le temporaire restant. Cette fonction
    suppose que le port a déjà été validé par son appelant.
    """
    # Créer le dossier parent avant d'écrire le fichier temporaire.
    config_dir = os.path.dirname(CONFIG_PATH)
    os.makedirs(config_dir, exist_ok=True)
    temp_path = None
    try:
        # Écrire d'abord une version complète du JSON, sans tronquer le fichier courant.
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=config_dir,
            delete=False
        ) as config_file:
            temp_path = config_file.name
            json.dump({"port": port}, config_file)
        # Le remplacement atomique évite qu'un lecteur voie un JSON partiellement écrit.
        os.replace(temp_path, CONFIG_PATH)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

def find_honeypot_processes(honeypot_script):
    """Recherche les processus qui exécutent précisément le script honeypot indiqué.

    Le chemin de référence est rendu absolu et normalisé avant comparaison avec les
    arguments de ligne de commande terminés par .py. Le processus courant est
    ignoré. Les processus terminés, inaccessibles ou zombies sont ignorés car ils
    ne peuvent pas être inspectés de manière fiable.

    Returns:
        Une liste d'objets psutil.Process correspondant au script.
    """
    # Normaliser le chemin de script pour comparer les chemins indépendamment de la casse Windows.
    target_script = os.path.normcase(os.path.abspath(honeypot_script))
    honeypot_processes = []
    # Itérer les processus en ne demandant que les champs utilisés pour réduire les lectures système.
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            # Ne jamais classer l'API elle-même comme instance à gérer.
            if proc.pid == os.getpid():
                continue
            cmdline = proc.info.get('cmdline') or []
            # Comparer les arguments Python plutôt que le nom de processus, commun à de nombreuses applications.
            if any(
                os.path.normcase(os.path.abspath(argument)) == target_script
                for argument in cmdline
                if argument.lower().endswith('.py')
            ):
                honeypot_processes.append(proc)
        # Le processus peut disparaître ou devenir inaccessible pendant l'énumération.
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return honeypot_processes

def get_honeypot_process_port(process, honeypot_script):
    """Détermine le port associé à un processus honeypot précis.

    Parcourt la ligne de commande pour trouver le chemin absolu du script demandé.
    Si l'argument qui suit est décimal, il est interprété comme le port explicite ;
    sinon le processus est traité comme l'instance principale et le port est lu
    depuis get_current_port. Si le script cible n'apparaît pas dans les arguments,
    la fonction renvoie None.
    """
    # Comparer le script réellement lancé avant d'interpréter le prochain argument comme un port.
    cmdline = process.info.get('cmdline') or []
    target_script = os.path.normcase(os.path.abspath(honeypot_script))
    for index, argument in enumerate(cmdline):
        if (
            argument.lower().endswith('.py')
            and os.path.normcase(os.path.abspath(argument)) == target_script
        ):
            # Un argument numérique après le script désigne explicitement le port de cette instance.
            if index + 1 < len(cmdline) and cmdline[index + 1].isdecimal():
                return int(cmdline[index + 1])
            # Sans port explicite, il s'agit de l'instance principale qui suit config.json.
            return get_current_port()
    # Ne pas associer un processus étranger à un port de honeypot.
    return None

def stop_honeypot_processes(processes):
    """Arrête une collection de processus avec une période de grâce de trois secondes.

    Envoie d'abord terminate() à chaque processus encore existant. Ensuite, attend
    la fin de chacun pendant trois secondes ; si le délai expire, envoie kill() et
    attend encore jusqu'à trois secondes. Les processus déjà disparus au moment de
    terminate ou wait sont ignorés.
    """
    # Envoyer terminate à tous les processus avant d'attendre, pour arrêter le groupe en parallèle.
    running_processes = []
    for proc in processes:
        try:
            proc.terminate()
            running_processes.append(proc)
        except psutil.NoSuchProcess:
            continue

    # Laisser trois secondes pour une fermeture propre, puis forcer les processus bloqués.
    for proc in running_processes:
        try:
            proc.wait(timeout=3)
        except psutil.NoSuchProcess:
            continue
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)

def start_honeypot(honeypot_script, port=None, *, archive=True):
    """Lance le script honeypot dans un nouveau processus Python.

    Utilise l'interpréteur courant et le dossier BASE_DIR comme répertoire de
    travail. Ajoute le port à la ligne de commande s'il est fourni. Le drapeau
    --no-archive désactive l'archivage pour les processus secondaires. Un délai
    d'une seconde permet de détecter un arrêt immédiat : un processus encore actif
    est retourné, tandis qu'un arrêt précoce déclenche RuntimeError.

    Returns:
        L'objet subprocess.Popen du processus lancé.
    """
    # Construire les arguments sans shell ; le paramètre archive désactive le worker d'archivage des instances secondaires.
    cmd = [sys.executable, honeypot_script]
    if port:
        cmd.append(str(port))
    if not archive:
        cmd.append('--no-archive')
    # Attendre brièvement pour détecter les échecs de démarrage avant de déclarer l'instance lancée.
    process = subprocess.Popen(cmd, cwd=BASE_DIR)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        return process
    raise RuntimeError(
        f"Le processus honeypot s'est arrêté au démarrage (code {process.returncode})."
    )


def get_record_page_parameters():
    """Lit et valide les paramètres de pagination et de filtre des routes de données.

    Les valeurs after_id, before_id, limit et port sont optionnelles ; celles qui
    sont présentes doivent être des chaînes décimales convertibles en entiers.
    limit est bornée par MAX_API_PAGE_SIZE, port par la plage 1-65535. Les deux
    curseurs de pagination sont mutuellement exclusifs.

    Returns:
        Un dictionnaire contenant chaque paramètre avec une valeur entière ou None.

    Raises:
        ValueError: si une valeur est mal formée, hors limites ou si les deux
            curseurs sont utilisés simultanément.
    """
    # Lire les quatre paramètres autorisés ; un paramètre absent est représenté par None.
    parameters = {}
    for name in ('after_id', 'before_id', 'limit', 'port'):
        raw_value = request.args.get(name)
        if raw_value is None:
            parameters[name] = None
            continue
        # Tous les paramètres sont des entiers positifs exprimés en décimal.
        if not raw_value.isdecimal():
            raise ValueError(f"Le paramètre '{name}' doit être un entier positif.")
        value = int(raw_value)
        # Appliquer les limites propres aux arguments qui en ont une.
        if name == 'limit' and not 1 <= value <= MAX_API_PAGE_SIZE:
            raise ValueError(
                f"Le paramètre 'limit' doit être compris entre 1 et {MAX_API_PAGE_SIZE}."
            )
        if name == 'port' and not 1 <= value <= 65535:
            raise ValueError("Le port doit être compris entre 1 et 65535.")
        parameters[name] = value
    # Un curseur avant et après n'a pas de sens dans la même requête.
    if parameters['after_id'] is not None and parameters['before_id'] is not None:
        raise ValueError("Les curseurs 'after_id' et 'before_id' ne peuvent pas être combinés.")
    return parameters


# --- ROUTES DE STATUT ET DE DONNÉES DU DASHBOARD ---

# Endpoint protégé : GET /api/status renvoie le statut global, le nombre de
# listeners actifs et leur inventaire (PID et port). Aucun paramètre n'est requis.
@app.route('/api/status', methods=['GET'])
def api_status():
    """Expose un résumé de l'état des listeners honeypot.

    Interroge find_all_honeypot_instances pour détecter les processus actifs,
    puis renvoie une réponse JSON contenant le statut textuel, un booléen active,
    le tableau instances et son nombre d'éléments.
    """
    # L'inventaire des processus est la source de vérité pour le statut du listener.
    instances = find_all_honeypot_instances()
    is_active = len(instances) > 0
    return jsonify({
        "status": "active" if is_active else "inactive",
        "active": is_active,
        "instances": instances,
        "count": len(instances)
    })

# Endpoint protégé : GET /api/attacks renvoie une page d'attaques.
# Query params optionnels : after_id ou before_id, limit (max 500), port.
# Paramètres incompatibles/invalides : HTTP 400 ; erreur de lecture : HTTP 500.
@app.route('/api/attacks', methods=['GET'])
def api_attacks():
    """Retourne une page d'attaques issues de la base SQLite.

    Valide les paramètres communs, puis transmet les curseurs after_id/before_id,
    la limite et le filtre port au helper de base de données. Les paramètres
    invalides sont renvoyés en HTTP 400. Les erreurs imprévues sont journalisées
    avec leur trace et renvoyées sous la forme d'une erreur HTTP 500 générique.
    """
    try:
        # Partager la validation des curseurs avec les autres endpoints paginés.
        parameters = get_record_page_parameters()
        # Seules les attaques acceptent aussi le filtre par port de honeypot.
        attacks = get_all_attacks(
            after_id=parameters['after_id'],
            before_id=parameters['before_id'],
            limit=parameters['limit'],
            port_filter=parameters['port']
        )
        return jsonify(attacks)
    except ValueError as error:
        # Les erreurs de saisie du client ne doivent pas être présentées comme des erreurs serveur.
        return jsonify({"error": str(error)}), 400
    except Exception:
        # Journaliser le détail interne, mais renvoyer une erreur générique au client.
        app.logger.exception('Impossible de récupérer les attaques.')
        return jsonify({"error": "Impossible de récupérer les attaques."}), 500

# Endpoint protégé : GET /api/commands renvoie une page de commandes capturées.
# Query params : after_id ou before_id et limit (max 500). Le port est accepté
# par le validateur commun mais n'est pas appliqué comme filtre par ce handler.
# Paramètres invalides : HTTP 400 ; erreur de lecture : HTTP 500.
@app.route('/api/commands', methods=['GET'])
def api_commands():
    """Retourne une page de commandes du faux shell.

    Les curseurs et la limite proviennent de get_record_page_parameters ; le filtre
    de port accepté par ce helper n'est pas appliqué à cette requête. Une valeur
    incorrecte produit HTTP 400. Une erreur de lecture est journalisée et masquée
    derrière une réponse HTTP 500.
    """
    try:
        # Valider les curseurs et la taille de page avant la requête SQL.
        parameters = get_record_page_parameters()
        # Les commandes sont paginées par ID ; leur association aux attaques est faite par le frontend.
        commands = get_all_commands(
            after_id=parameters['after_id'],
            before_id=parameters['before_id'],
            limit=parameters['limit']
        )
        return jsonify(commands)
    except ValueError as error:
        # Retourner les paramètres incorrects au client avec le statut de validation.
        return jsonify({"error": str(error)}), 400
    except Exception:
        # Garder les détails dans les logs plutôt que dans la réponse API.
        app.logger.exception('Impossible de récupérer les commandes.')
        return jsonify({"error": "Impossible de récupérer les commandes."}), 500


# Endpoint protégé : GET /api/country-updates/latest renvoie {"id": N},
# curseur utilisé par le frontend pour ne récupérer ensuite que les nouveaux pays.
@app.route('/api/country-updates/latest', methods=['GET'])
def api_latest_country_update():
    """Expose le dernier identifiant GeoIP afin que le frontend initialise son curseur.

    La route renvoie un objet JSON de la forme {"id": ...}, où l'identifiant est
    calculé par le helper de base de données et peut valoir zéro si aucune mise à
    jour n'existe.
    """
    # Ce curseur permet au frontend de ne demander ensuite que les nouveaux pays résolus.
    return jsonify({"id": get_latest_country_update_id()})


# Endpoint protégé : GET /api/country-updates renvoie les enrichissements GeoIP.
# Query params : after_id ou before_id et limit (max 500). Paramètres invalides :
# HTTP 400 ; erreur de lecture : HTTP 500.
@app.route('/api/country-updates', methods=['GET'])
def api_country_updates():
    """Retourne les résultats GeoIP ajoutés aux attaques après leur capture.

    Les mises à jour ont leur propre flux et leur propre pagination, ce qui évite
    de recharger les attaques pour afficher les pays résolus en arrière-plan.
    Les erreurs de paramètres deviennent HTTP 400 ; les autres erreurs sont
    consignées et deviennent HTTP 500.
    """
    try:
        # Utiliser les mêmes limites de pagination que pour les autres flux d'enregistrements.
        parameters = get_record_page_parameters()
        # Les updates GeoIP sont renvoyés séparément des tentatives initiales.
        updates = get_country_updates(
            after_id=parameters['after_id'],
            before_id=parameters['before_id'],
            limit=parameters['limit']
        )
        return jsonify(updates)
    except ValueError as error:
        # Signaler les paramètres invalides comme une erreur de requête.
        return jsonify({"error": str(error)}), 400
    except Exception:
        # Logger l'exception complète pour diagnostic, sans divulguer sa trace au client.
        app.logger.exception('Impossible de récupérer les mises à jour de pays.')
        return jsonify({"error": "Impossible de récupérer les mises à jour de pays."}), 500

# Endpoint protégé : GET /api/stats renvoie les agrégats calculés par la couche
# SQLite (totaux et indicateurs du dashboard). Aucun paramètre n'est requis.
# Une erreur de calcul ou de lecture est renvoyée en HTTP 500.
@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Retourne les indicateurs calculés par get_stats à partir des données persistées.

    Le helper de base de données fournit l'objet de statistiques sérialisé en JSON.
    Toute exception est convertie en réponse HTTP 500 dont le champ error contient
    son message.
    """
    try:
        # Déléguer les agrégations SQL à la couche de persistance.
        stats = get_stats()
        return jsonify(stats)
    except Exception as e:
        # Convertir l'échec de calcul/lecture en réponse JSON d'erreur.
        return jsonify({"error": str(e)}), 500


# --- ROUTES DE GESTION DU DECEPTION MESH (MULTI-HONEYPOTS) ---

def find_all_honeypot_instances():
    """Construit un inventaire ordonné des processus du listener SSH du projet.

    Utilise le chemin du script honeypot.py comme identité, détermine le port de
    chaque processus puis conserve les entrées ayant un port reconnu. Les processus
    devenus inaccessibles ou terminés pendant l'inspection sont écartés. Le résultat
    est trié d'abord par port, puis par PID.
    """
    # Le script situé dans le même dossier que cette API identifie les processus gérés.
    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    instances = []
    # Chaque processus détecté est traduit en données sérialisables pour l'API.
    for proc in find_honeypot_processes(honeypot_script):
        try:
            port = get_honeypot_process_port(proc, honeypot_script)
            if port is not None:
                instances.append({"pid": proc.pid, "port": port})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Ignorer un processus qui a disparu ou est devenu inaccessible au milieu du scan.
            continue
    # Un ordre stable simplifie l'affichage du mesh dans le tableau de bord.
    return sorted(instances, key=lambda instance: (instance['port'], instance['pid']))

# Endpoint protégé : GET /api/honeypots renvoie {"honeypots": [...]} avec le
# PID et le port de chaque processus correspondant au listener du projet.
@app.route('/api/honeypots', methods=['GET'])
def api_list_honeypots():
    """Renvoie l'inventaire des listeners actuellement actifs.

    La réponse utilise la clé honeypots et délègue la détection et le tri à
    find_all_honeypot_instances.
    """
    # Garder une enveloppe JSON nommée pour fournir une réponse extensible.
    return jsonify({"honeypots": find_all_honeypot_instances()})

# Endpoint protégé : POST /api/honeypots attend {"port": N} pour démarrer un
# listener. Port hors plage ou corps invalide : HTTP 400 ; port occupé : HTTP 409 ;
# lancement impossible : HTTP 500 ; succès : PID et port du nouveau processus.
@app.route('/api/honeypots', methods=['POST'])
def api_start_honeypot():
    """Démarre une instance SSH sur un port fourni dans le corps JSON.

    Refuse les corps incomplets, les booléens et les ports qui ne sont pas des
    entiers entre 1 et 65535. Sous HONEYPOT_LOCK, vérifie que le port n'est pas
    déjà attribué à un honeypot et qu'il peut être bindé sur toutes les interfaces.
    Lance ensuite une instance secondaire sans archivage. Les conflits donnent
    HTTP 409, les erreurs de lancement HTTP 500 et le succès renvoie PID et port.
    """
    # Vérifier la structure puis le type avant la conversion pour exclure notamment les booléens.
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or 'port' not in data:
        return jsonify({"error": "Port manquant."}), 400
    # Une chaîne de port doit être entièrement numérique et ne pas dépasser cinq chiffres.
    value = data['port']
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return jsonify({"error": "Le port doit être un nombre entier."}), 400
    if isinstance(value, str) and (not value.isdecimal() or len(value) > 5):
        return jsonify({"error": "Le port doit être un nombre entier."}), 400
    port = int(value)

    # La plage réseau standard contient les ports 1 à 65535.
    if not 1 <= port <= 65535:
        return jsonify({"error": "Le port doit être compris entre 1 et 65535."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    with HONEYPOT_LOCK:
        # Le verrou évite deux démarrages simultanés du même port par cette API.
        if any(instance['port'] == port for instance in find_all_honeypot_instances()):
            return jsonify({"error": f"Un honeypot écoute déjà sur le port {port}."}), 409

        # Tester la disponibilité réelle du port sur toutes les interfaces IPv4.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("0.0.0.0", port))
        except OSError:
            return jsonify({"error": f"Le port {port} est déjà utilisé ou indisponible."}), 409

        # Les workers secondaires ne doivent pas lancer chacun une tâche d'archivage.
        try:
            process = start_honeypot(honeypot_script, port=port, archive=False)
        except (OSError, RuntimeError) as error:
            return jsonify({"error": f"Échec du lancement du honeypot : {error}"}), 500

    # Renvoyer les informations du processus démarré pour rafraîchir l'interface.
    return jsonify({
        "success": True,
        "message": f"Faux SSH déployé avec succès sur le port {port}.",
        "pid": process.pid,
        "port": port
    })

# Endpoint protégé : POST /api/honeypots/swarm attend count, port_min et
# port_max. count doit être entre 1 et 10 ; les ports libres sont sélectionnés
# aléatoirement dans la plage. Renvoie HTTP 409 si la capacité est insuffisante ;
# la réponse de succès distingue les instances déployées des erreurs individuelles.
@app.route('/api/honeypots/swarm', methods=['POST'])
def api_start_swarm():
    """Déploie plusieurs listeners sur des ports libres choisis dans une plage.

    Le corps JSON doit fournir count, port_min et port_max ; count est limité à
    1-10 et la plage de ports doit être croissante et comprise entre 1 et 65535.
    Sous HONEYPOT_LOCK, examine les ports de la plage, retire les ports déjà
    actifs et teste la disponibilité réelle avec bind. Si le nombre de ports
    libres est insuffisant, renvoie HTTP 409 sans lancer d'instance. Sinon,
    sélectionne aléatoirement les ports demandés et tente chaque démarrage,
    en renvoyant séparément les instances lancées et les erreurs par port.
    """
    # Extraire les paramètres requis ; la conversion est entourée pour répondre proprement aux valeurs invalides.
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

    # Borner le nombre d'instances et valider l'ordre et les limites de la plage.
    if not (1 <= count <= 10):
        return jsonify({"error": "Le nombre de honeypots doit être compris entre 1 et 10."}), 400
    if not (1 <= port_min <= 65535 and 1 <= port_max <= 65535 and port_min <= port_max):
        return jsonify({"error": "La plage de ports est invalide (1-65535)."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    
    with HONEYPOT_LOCK:
        # Écarter les ports déjà attribués, puis tester le bind des autres candidats.
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

        # Ne rien lancer si la plage ne peut pas satisfaire toute la demande.
        if len(available_ports) < count:
            return jsonify({
                "error": f"Capacité insuffisante : Seulement {len(available_ports)} ports disponibles trouvés dans la plage [{port_min}, {port_max}] pour {count} demandés."
            }), 409

        # Tirer les ports aléatoirement parmi les ports libres et tenter chaque lancement.
        selected_ports = random.sample(available_ports, count)
        deployed_instances = []
        errors = []

        for p in selected_ports:
            try:
                process = start_honeypot(honeypot_script, port=p, archive=False)
                deployed_instances.append({"port": p, "pid": process.pid})
            except (OSError, RuntimeError) as error:
                errors.append(f"Port {p}: {str(error)}")

    # La réponse distingue les processus créés des erreurs individuelles.
    return jsonify({
        "success": True,
        "deployed": deployed_instances,
        "errors": errors,
        "message": f"{len(deployed_instances)} faux SSH déployés en essaim avec succès."
    })

# Endpoint protégé : POST /api/honeypots/swarm-reference attend count et
# reference_port. Cherche les ports disponibles autour de ce port (count max 10),
# puis renvoie les processus créés et leurs erreurs éventuelles. Paramètres
# invalides : HTTP 400 ; nombre de ports libres insuffisant : HTTP 409.
@app.route('/api/honeypots/swarm-reference', methods=['POST'])
def api_start_swarm_reference():
    """Déploie des listeners sur les ports libres proches d'un port de référence.

    Valide count (1-10) et reference_port (1-65535). Sous HONEYPOT_LOCK, génère
    des candidats alternativement au-dessus et au-dessous du port de référence,
    en explorant au plus trois fois le nombre d'instances demandé. Les ports déjà
    actifs et ceux qui ne peuvent pas être bindés sont ignorés. Si le nombre de
    ports disponibles est insuffisant, renvoie HTTP 409 ; sinon, lance les
    processus trouvés et rapporte séparément les succès et les erreurs.
    """
    # Lire et convertir la quantité demandée et le port de référence.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Corps de requête invalide."}), 400
    
    count_val = data.get('count')
    ref_val = data.get('reference_port')

    try:
        count = int(count_val)
        ref_port = int(ref_val)
    except (TypeError, ValueError):
        return jsonify({"error": "Les paramètres 'count' et 'reference_port' doivent être des nombres entiers."}), 400

    # Limiter le nombre d'instances et s'assurer que le port de référence existe.
    if not (1 <= count <= 10):
        return jsonify({"error": "Le nombre de honeypots doit être compris entre 1 et 10."}), 400
    if not (1 <= ref_port <= 65535):
        return jsonify({"error": "Le port de référence doit être compris entre 1 et 65535."}), 400

    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    
    with HONEYPOT_LOCK:
        # Préparer les ports candidats en alternant au-dessus et au-dessous du port de référence.
        active_ports = {instance['port'] for instance in find_all_honeypot_instances()}
        
        candidate_ports = []
        offset = 1
        while len(candidate_ports) < (count * 3):
            p_up = ref_port + offset
            p_down = ref_port - offset
            if p_up <= 65535 and p_up != ref_port:
                candidate_ports.append(p_up)
            if p_down >= 1 and p_down != ref_port:
                candidate_ports.append(p_down)
            if p_up > 65535 and p_down < 1:
                break
            offset += 1

        # Garder uniquement les candidats non actifs et réellement bindables, dans l'ordre de proximité.
        available_ports = []
        for p in candidate_ports:
            if len(available_ports) >= count:
                break
            if p in active_ports:
                continue
            
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind(("0.0.0.0", p))
                available_ports.append(p)
            except OSError:
                continue

        # Ne pas commencer un déploiement partiel si la quantité de ports disponibles est insuffisante.
        if len(available_ports) < count:
            return jsonify({
                "error": f"Impossible de trouver {count} ports libres autour du service {ref_port}. Seulement {len(available_ports)} disponibles."
            }), 409

        # Lancer les ports disponibles et conserver les échecs par port dans la réponse.
        deployed_instances = []
        errors = []

        for p in available_ports:
            try:
                process = start_honeypot(honeypot_script, port=p, archive=False)
                deployed_instances.append({"port": p, "pid": process.pid})
            except (OSError, RuntimeError) as error:
                errors.append(f"Port {p}: {str(error)}")

    # Retourner simultanément le nombre de succès et les éventuelles erreurs de lancement.
    return jsonify({
        "success": True,
        "deployed": deployed_instances,
        "errors": errors,
        "message": f"{len(deployed_instances)} honeypots déployés autour du service sur le port {ref_port} avec succès."
    })

# Endpoint protégé : DELETE /api/honeypots/<port> arrête les processus du listener
# qui utilisent ce port. Répond HTTP 404 si aucun processus n'est trouvé,
# HTTP 500 si l'arrêt échoue, sinon confirme l'arrêt.
@app.route('/api/honeypots/<int:port>', methods=['DELETE'])
def api_stop_honeypot(port):
    """Arrête le ou les processus honeypot identifiés par le port d'URL.

    Sous HONEYPOT_LOCK, détecte les processus correspondant au script du projet et
    filtre ceux dont le port calculé correspond au paramètre de route. Renvoie
    HTTP 404 si aucun processus ne correspond. Sinon, délègue l'arrêt gracieux
    puis forcé à stop_honeypot_processes ; les échecs de processus renvoient
    HTTP 500 et un arrêt réussi renvoie un message de confirmation.
    """
    # Construire la liste des processus du script dont le port correspond au paramètre de route.
    honeypot_script = os.path.join(BASE_DIR, 'honeypot.py')
    with HONEYPOT_LOCK:
        matches = [
            proc for proc in find_honeypot_processes(honeypot_script)
            if get_honeypot_process_port(proc, honeypot_script) == port
        ]
        # Un port sans processus correspondant ne nécessite aucune commande système.
        if not matches:
            return jsonify({"error": f"Aucun faux SSH actif trouvé sur le port {port}."}), 404

        # Déléguer terminate/wait/kill au helper commun.
        try:
            stop_honeypot_processes(matches)
        except (psutil.Error, OSError) as error:
            return jsonify({"error": f"Impossible d'arrêter le honeypot sur le port {port} : {error}"}), 500

    # Confirmer l'arrêt seulement après la fin des processus associés.
    return jsonify({"success": True, "message": f"Faux SSH sur le port {port} arrêté avec succès."})


# --- FONCTIONS DE DÉFENSE ACTIVE (FIREWALL) ---

def run_firewall_command(command, check=True):
    """Exécute une commande système de pare-feu et normalise les erreurs d'exécution.

    Sous Linux/Unix, ajoute sudo -n si l'API n'est pas root afin qu'aucune invite
    interactive de mot de passe ne bloque le serveur. Capture stdout/stderr avec
    un délai maximal de dix secondes. Les erreurs de lancement et de délai sont
    converties en RuntimeError ; si check=True, un code retour non nul l'est
    également. Avec check=False, le CompletedProcess est retourné pour que
    l'appelant puisse interpréter le code retour comme un état attendu.
    """
    # Les systèmes de type Unix requièrent root ; sudo -n échoue sans interaction si les droits manquent.
    if os.name != 'nt' and os.geteuid() != 0:
        command = ['sudo', '-n', *command]

    try:
        # Capturer les sorties et fixer un délai pour que l'API ne reste pas bloquée sur un outil système.
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
        # Utiliser le diagnostic le plus utile disponible pour l'exception applicative.
        details = result.stderr.strip() or result.stdout.strip() or f"code {result.returncode}"
        raise RuntimeError(details)
    return result

def windows_firewall_rule_name(ip_address):
    """Produit le nom déterministe de règle Windows utilisé pour une adresse IP.

    Le SHA-256 est calculé sur l'adresse normalisée en ASCII, puis tronqué à
    16 caractères hexadécimaux. Le préfixe propre à l'application permet de
    retrouver et supprimer ultérieurement la règle correspondante.
    """
    # Un nom dérivé de l'adresse évite d'y intégrer directement des caractères arbitraires.
    digest = hashlib.sha256(ip_address.encode('ascii')).hexdigest()[:16]
    return f"WinnieThePooh-Honeypot-{digest}"

def linux_firewall_command(ip_address):
    """Choisit l'outil Linux correspondant à la famille IPv4 ou IPv6.

    ipaddress.ip_address valide et interprète l'adresse ; sa version 4 sélectionne
    iptables, tandis que la version 6 sélectionne ip6tables.
    """
    # ipaddress lève ValueError pour une adresse mal formée au lieu de choisir un outil arbitraire.
    return 'iptables' if ipaddress.ip_address(ip_address).version == 4 else 'ip6tables'

def linux_rule_exists(command, chain, ip_address):
    """Interroge netfilter pour savoir si une règle DROP exacte est présente.

    Exécute la commande de vérification -C sur la chaîne, la source et la cible
    DROP fournies. check=False permet qu'une règle absente soit interprétée via
    son code retour plutôt que levée comme une exception.
    """
    # -C teste la règle sans la modifier ; un code retour nul signifie qu'elle existe.
    result = run_firewall_command(
        [command, '-C', chain, '-s', ip_address, '-j', 'DROP'],
        check=False
    )
    return result.returncode == 0

def load_banned_ips():
    """Charge et valide la liste JSON persistée des adresses bannies.

    Si le fichier n'existe pas, aucun bannissement local n'est enregistré et une
    liste vide est renvoyée. Les erreurs d'accès ou de décodage JSON, ainsi qu'une
    racine qui n'est pas une liste de chaînes, sont converties en RuntimeError
    pour que l'API puisse signaler une panne d'état plutôt que la masquer.
    """
    # Un fichier absent est l'état initial valide : aucune adresse n'est bannie par l'application.
    if not os.path.exists(BAN_STATE_PATH):
        return []
    try:
        # Charger le document complet avant d'en valider la structure.
        with open(BAN_STATE_PATH, 'r', encoding='utf-8') as state_file:
            ips = json.load(state_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Impossible de lire l'état des IP bannies : {error}") from error
    # Éviter qu'une donnée JSON inattendue soit ensuite traitée comme une liste d'adresses.
    if not isinstance(ips, list) or any(not isinstance(ip, str) for ip in ips):
        raise RuntimeError("Le fichier d'état des IP bannies est invalide.")
    return ips

def save_banned_ips(ips):
    """Sauvegarde la liste d'adresses bannies sous forme JSON triée et dédupliquée.

    Le dossier est créé au besoin ; les valeurs sont converties en ensemble puis
    triées avant sérialisation. Un fichier temporaire placé dans le dossier cible
    est remplacé atomiquement par BAN_STATE_PATH. Les problèmes d'écriture sont
    remontés en RuntimeError, et le fichier temporaire restant est nettoyé.
    """
    # Placer le temporaire près de la destination afin que le remplacement reste atomique.
    state_dir = os.path.dirname(BAN_STATE_PATH)
    temp_path = None
    try:
        os.makedirs(state_dir, exist_ok=True)
        # Dédupliquer et ordonner pour obtenir un fichier stable entre deux sauvegardes identiques.
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=state_dir,
            delete=False
        ) as state_file:
            temp_path = state_file.name
            json.dump(sorted(set(ips)), state_file)
        # Publier le nouveau JSON d'un seul remplacement après fermeture du fichier.
        os.replace(temp_path, BAN_STATE_PATH)
    except OSError as error:
        raise RuntimeError(f"Impossible d'enregistrer l'état des IP bannies : {error}") from error
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

def ban_ip_system(ip_address):
    """Installe dans le pare-feu système une règle bloquant une adresse entrante.

    L'adresse est d'abord normalisée par ipaddress. Sous Windows, crée une règle
    Defender Firewall nommée de manière déterministe et configurée pour bloquer
    le trafic entrant provenant de cette IP. Sous Linux, choisit iptables ou
    ip6tables, crée si nécessaire la chaîne dédiée WINNIE_HONEYPOT, vérifie
    l'existence de cette chaîne, s'assure qu'INPUT y redirige le trafic puis
    ajoute la règle DROP seulement si elle n'existe pas déjà. Les commandes
    indispensables qui échouent sont remontées comme RuntimeError.
    """
    # Canonicaliser l'adresse avant de la transmettre aux outils du système.
    parsed_ip = ipaddress.ip_address(ip_address)
    ip_address = str(parsed_ip)
    if os.name == 'nt':
        # Windows reçoit une règle entrante dont le nom peut être recalculé pour le débannissement.
        run_firewall_command([
            'netsh', 'advfirewall', 'firewall', 'add', 'rule',
            f"name={windows_firewall_rule_name(ip_address)}",
            'dir=in', 'action=block', f"remoteip={ip_address}", 'enable=yes'
        ])
        return

    # Sous Linux, créer une chaîne dédiée et un seul saut depuis INPUT vers cette chaîne.
    command = linux_firewall_command(ip_address)
    chain = 'WINNIE_HONEYPOT'
    run_firewall_command([command, '-N', chain], check=False)
    run_firewall_command([command, '-S', chain])
    # Ajouter le saut au début d'INPUT uniquement s'il n'est pas déjà présent.
    input_jump = run_firewall_command(
        [command, '-C', 'INPUT', '-j', chain],
        check=False
    )
    if input_jump.returncode:
        run_firewall_command([command, '-I', 'INPUT', '1', '-j', chain])
    # Ne pas dupliquer une règle DROP existante pour la même source.
    if not linux_rule_exists(command, chain, ip_address):
        run_firewall_command([command, '-A', chain, '-s', ip_address, '-j', 'DROP'])

def unban_ip_system(ip_address):
    """Supprime du pare-feu les règles de blocage associées à une adresse IP.

    Étapes :
      1. Parse l'adresse et la normalise, ce qui sélectionne aussi sa famille IP.
      2. Sous Windows, recalcule le nom déterministe créé par
         windows_firewall_rule_name, supprime cette règle via netsh, puis retourne.
      3. Sous Linux, sélectionne iptables ou ip6tables et vérifie que la chaîne
         INPUT peut être interrogée.
      4. Cherche les règles DROP exactes dans la chaîne dédiée
         WINNIE_HONEYPOT puis dans INPUT.
      5. Supprime chaque occurrence trouvée, en répétant la vérification jusqu'à
         ce qu'il n'en reste plus.

    Les commandes passent par run_firewall_command : une erreur d'exécution ou
    une erreur de suppression est remontée à l'appelant. Cette fonction ne met
    pas à jour banned_ips.json ; cette responsabilité appartient à api_unban_ip.
    """
    parsed_ip = ipaddress.ip_address(ip_address)
    # La forme canonique garantit que la même IP produit le même nom de règle et les mêmes arguments firewall.
    ip_address = str(parsed_ip)
    if os.name == 'nt':
        # Windows n'expose pas ici de chaîne partagée : supprimer la règle nommée suffit.
        run_firewall_command([
            'netsh', 'advfirewall', 'firewall', 'delete', 'rule',
            f"name={windows_firewall_rule_name(ip_address)}"
        ])
        return

    # Linux utilise l'outil adapté à la version IPv4/IPv6 de l'adresse.
    command = linux_firewall_command(ip_address)
    # Vérifie INPUT avant de rechercher/supprimer des règles dans les chaînes gérées.
    run_firewall_command([command, '-S', 'INPUT'])
    # Retire les occurrences dans la chaîne dédiée et dans INPUT pour nettoyer aussi
    # les règles directes éventuellement créées par d'anciennes versions.
    for chain in ('WINNIE_HONEYPOT', 'INPUT'):
        while linux_rule_exists(command, chain, ip_address):
            # La boucle est volontaire : plusieurs copies identiques peuvent exister.
            run_firewall_command([command, '-D', chain, '-s', ip_address, '-j', 'DROP'])

# Endpoint protégé : POST /api/ban attend {"ip": "..."}.
# Valide l'IP, refuse les loopback, applique le blocage au pare-feu hôte et
# persiste l'adresse. IP/corps invalide : HTTP 400 ; échec système ou stockage : HTTP 500.
@app.route('/api/ban', methods=['POST'])
def api_ban_ip():
    """Valide une adresse puis applique et persiste son bannissement.

    Le corps JSON doit contenir ip sous forme de chaîne. Les adresses invalides et
    les adresses loopback sont refusées pour éviter de couper l'accès local. Sous
    BAN_LOCK, la règle système est appliquée avant que la liste JSON soit actualisée ;
    l'entrée est ajoutée uniquement si elle n'y figure pas déjà. Les erreurs
    d'exécution ou d'état sont renvoyées en HTTP 500.
    """
    # Exiger un objet JSON avec une IP texte et la faire parser par la bibliothèque standard.
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('ip'), str):
        return jsonify({"error": "Adresse IP manquante."}), 400
    try:
        parsed_ip = ipaddress.ip_address(data['ip'].strip())
    except ValueError:
        return jsonify({"error": "L'adresse IP fournie est invalide."}), 400
    # Préserver l'accès local au tableau de bord en refusant tout bannissement loopback.
    if parsed_ip.is_loopback:
        return jsonify({
            "error": "Une adresse loopback (127.0.0.1 ou ::1) ne peut pas être bannie."
        }), 400
    target_ip = str(parsed_ip)

    # Protéger ensemble la modification système et la mise à jour du fichier local.
    try:
        with BAN_LOCK:
            ban_ip_system(target_ip)
            banned_ips = load_banned_ips()
            if target_ip not in banned_ips:
                banned_ips.append(target_ip)
                save_banned_ips(banned_ips)
    except RuntimeError as error:
        return jsonify({"error": f"Échec du bannissement de l'IP {target_ip} : {error}"}), 500

    # Le succès signifie que la règle système et l'état persisté ont tous deux été mis à jour.
    return jsonify({"success": True, "message": f"IP {target_ip} bannie avec succès du pare-feu."})

# Endpoint protégé : POST /api/unban attend {"ip": "..."}.
# Supprime les règles pare-feu, retire l'adresse du fichier d'état et efface
# ses statistiques d'auto-ban. IP/corps invalide : HTTP 400 ; échec : HTTP 500.
@app.route('/api/unban', methods=['POST'])
def api_unban_ip():
    """Retire le bannissement système et sa trace dans l'état local.

    Valide la chaîne IP, puis prend BAN_LOCK pour coordonner cette opération avec
    les bannissements et rapports concurrents. Supprime d'abord les règles du
    pare-feu, enregistre ensuite une liste sans l'adresse et retire enfin ses
    statistiques auto-ban éventuelles. Une erreur système ou de sauvegarde
    renvoie HTTP 500 ; le verrou est libéré automatiquement à la sortie du bloc.
    """
    # Vérifier la présence d'une adresse sous forme texte, puis normaliser IPv4/IPv6.
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('ip'), str):
        return jsonify({"error": "Adresse IP manquante."}), 400
    # Maintenir la cohérence entre pare-feu, JSON persistant et statistiques en mémoire.
    try:
        target_ip = str(ipaddress.ip_address(data['ip'].strip()))
    except ValueError:
        return jsonify({"error": "L'adresse IP fournie est invalide."}), 400

    try:
        with BAN_LOCK:
            unban_ip_system(target_ip)
            save_banned_ips([ip for ip in load_banned_ips() if ip != target_ip])
            if target_ip in AUTO_BAN_STATS:
                del AUTO_BAN_STATS[target_ip]
    except RuntimeError as error:
        return jsonify({"error": f"Échec du débannissement de l'IP {target_ip} : {error}"}), 500

    # N'accuser réception qu'après le retrait dans les trois emplacements concernés.
    return jsonify({"success": True, "message": f"IP {target_ip} débannie avec succès du pare-feu."})

# Endpoint protégé : GET /api/banned-ips renvoie {"ips": [...]} depuis le fichier
# d'état local ; un fichier absent donne une liste vide, un fichier illisible HTTP 500.
@app.route('/api/banned-ips', methods=['GET'])
def api_banned_ips():
    """Retourne la liste JSON des IP bannies enregistrées par l'application.

    Une liste vide est renvoyée si le fichier d'état n'existe pas. Un fichier
    corrompu ou inaccessible est signalé au client en HTTP 500.
    """
    try:
        # L'endpoint reflète le fichier local ; il ne reconstitue pas les règles externes du système.
        return jsonify({"ips": load_banned_ips()})
    except RuntimeError as error:
        # Une liste illisible ne doit pas être présentée comme une liste vide.
        return jsonify({"error": str(error)}), 500

# Endpoint protégé : GET /api/autoban-stats renvoie les statistiques en mémoire
# des adresses automatiquement bannies. Les compteurs disparaissent au redémarrage.
@app.route('/api/autoban-stats', methods=['GET'])
def api_autoban_stats():
    """Renvoie les compteurs d'auto-ban actuellement conservés en mémoire.

    BAN_LOCK empêche qu'une lecture observe un dictionnaire en cours de modification
    par une route de bannissement ou de rapport de tentative.
    """
    with BAN_LOCK:
        # Les compteurs sont en mémoire et ne survivent pas au redémarrage du serveur.
        return jsonify({"autoban_stats": AUTO_BAN_STATS})

# Endpoint protégé : GET /api/autoban-config renvoie les réglages actuels ;
# POST accepte enabled, window (1-300 s) et max_attempts (1-100).
# Les mises à jour sont partielles, en mémoire uniquement ; corps JSON invalide : HTTP 400.
@app.route('/api/autoban-config', methods=['GET', 'POST'])
def api_autoban_config():
    """Expose ou modifie les paramètres en mémoire de la défense automatique.

    GET renvoie l'activation, la fenêtre temporelle et le seuil courant. POST
    attend un objet JSON et met à jour uniquement les champs transmis, sous
    BAN_LOCK : enabled est converti en booléen, window doit être entre 1 et 300
    secondes et max_attempts entre 1 et 100. Les conversions invalides ou valeurs
    hors limites des champs numériques sont ignorées ; ces réglages ne sont pas
    persistés et reviennent aux valeurs par défaut au redémarrage du processus.
    """
    global AUTO_BAN_ENABLED, RATE_LIMIT_WINDOW, RATE_LIMIT_MAX_ATTEMPTS
    if request.method == 'GET':
        # Lire les valeurs effectives sans les persister.
        return jsonify({
            "enabled": AUTO_BAN_ENABLED,
            "window": RATE_LIMIT_WINDOW,
            "max_attempts": RATE_LIMIT_MAX_ATTEMPTS
        })
    
    # Les modifications requièrent un objet JSON ; les paramètres absents conservent leur valeur.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Corps de requête invalide."}), 400

    with BAN_LOCK:
        # Appliquer séparément chaque champ afin qu'une mise à jour partielle soit permise.
        if 'enabled' in data:
            AUTO_BAN_ENABLED = bool(data['enabled'])
        if 'window' in data:
            # Ignorer les conversions impossibles ou les valeurs hors des bornes acceptées.
            try:
                val = int(data['window'])
                if 1 <= val <= 300:
                    RATE_LIMIT_WINDOW = val
            except (ValueError, TypeError):
                pass
        if 'max_attempts' in data:
            # Même politique de validation indépendante pour le seuil d'essais.
            try:
                val = int(data['max_attempts'])
                if 1 <= val <= 100:
                    RATE_LIMIT_MAX_ATTEMPTS = val
            except (ValueError, TypeError):
                pass

    # Renvoyer l'état final pour que le client puisse synchroniser ses contrôles.
    return jsonify({
        "success": True,
        "enabled": AUTO_BAN_ENABLED,
        "window": RATE_LIMIT_WINDOW,
        "max_attempts": RATE_LIMIT_MAX_ATTEMPTS
    })

# Endpoint protégé : GET /api/attempt-stats compte les tentatives par IP encore
# dans la fenêtre courante et renvoie {"active_attempts": {ip: count}}.
@app.route('/api/attempt-stats', methods=['GET'])
def api_attempt_stats():
    """Compte les tentatives en mémoire qui sont encore dans la fenêtre de limitation.

    Pour chaque adresse de ATTEMPT_HISTORY, ne compte que les horodatages dont
    l'âge est strictement inférieur à RATE_LIMIT_WINDOW. Les adresses sans
    tentative récente ne figurent pas dans active_attempts. Le verrou protège
    la lecture pendant qu'une autre requête met à jour l'historique.
    """
    # Capturer une seule référence temporelle afin de calculer tous les âges de façon cohérente.
    now = time.time()
    with BAN_LOCK:
        # Filtrer la fenêtre pour chaque IP puis omettre les adresses sans activité récente.
        active_attempts = {}
        for ip, timestamps in ATTEMPT_HISTORY.items():
            valid_ts = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
            if valid_ts:
                active_attempts[ip] = len(valid_ts)
    # Fournir au client le nombre d'essais courants par adresse.
        return jsonify({"active_attempts": active_attempts})

# Endpoint intentionnellement public (exempté de protect_api) : POST
# /api/report-attempt attend {"ip": "..."}, ajoute une tentative à la fenêtre
# en mémoire et déclenche l'auto-ban si activé et au seuil. Loopback ignorée ;
# corps/IP invalide : HTTP 400. Ne pas exposer cette route à des clients non fiables.
@app.route('/api/report-attempt', methods=['POST'])
def api_report_attempt():
    """Ajoute une tentative signalée à l'historique de limitation par adresse.

    Attend une IP textuelle, la valide et ignore sans pénalité les adresses
    loopback. Sous BAN_LOCK, les IP déjà bannies ne sont pas recomptées. Pour les
    autres, supprime les timestamps antérieurs à la fenêtre courante, ajoute
    l'instant présent puis compare le nombre obtenu au seuil configuré.
    Si l'auto-ban est activé et que le seuil est atteint, applique la règle système,
    persiste l'adresse bannie et mémorise son compteur. Les erreurs du pare-feu
    sont journalisées sans annuler la réponse de suivi de tentative.
    """
    # Refuser une requête sans IP textuelle avant toute mutation de l'historique.
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('ip'), str):
        return jsonify({"error": "IP manquante."}), 400

    # Les IP loopback sont ignorées ; les autres adresses sont canonicalisées.
    try:
        parsed_ip = ipaddress.ip_address(data['ip'].strip())
        if parsed_ip.is_loopback:
            return jsonify({"success": True, "ignored": "loopback"})
        target_ip = str(parsed_ip)
    except ValueError:
        return jsonify({"error": "IP invalide."}), 400

    # Garder synchronisées l'historique, les règles système et l'état persistant sous le même verrou.
    now = time.time()
    with BAN_LOCK:
        banned_ips = load_banned_ips()
        # Une IP déjà bannie n'a pas besoin d'accumuler de nouveaux essais.
        if target_ip in banned_ips:
            return jsonify({"success": True, "status": "already_banned"})

        # Supprimer les essais hors fenêtre, puis compter l'essai présent dans cette demande.
        timestamps = ATTEMPT_HISTORY[target_ip]
        timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
        timestamps.append(now)
        ATTEMPT_HISTORY[target_ip] = timestamps
        current_attempts = len(timestamps)

        # Déclencher le ban au seuil atteint ; conserver le compteur associé aux stats auto-ban.
        if AUTO_BAN_ENABLED and current_attempts >= RATE_LIMIT_MAX_ATTEMPTS:
            try:
                ban_ip_system(target_ip)
                if target_ip not in banned_ips:
                    banned_ips.append(target_ip)
                    save_banned_ips(banned_ips)
                
                AUTO_BAN_STATS[target_ip] = current_attempts
            except RuntimeError as error:
                app.logger.error(f"Échec auto-ban IP {target_ip} : {error}")

    return jsonify({"success": True, "current_attempts": current_attempts})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)