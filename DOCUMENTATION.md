1. User Stories et Maquettes1.1 Liste des User Stories (Priorisées MoSCoW)[Must Have] Capture des connexions SSHEn tant qu' administrateur de sécurité,Je veux que le honeypot écoute sur un port dédié et intercepte les tentatives de connexion SSH,Afin de capturer les identifiants (utilisateurs et mots de passe) testés par les bots ou attaquants.[Must Have] Stockage persistantEn tant qu' administrateur de sécurité,Je veux que chaque tentative d'attaque capturée soit enregistrée de manière permanente dans une base de données,Afin de conserver l'historique lors du redémarrage des services.[Must Have] Affichage du tableau de bordEn tant qu' administrateur de sécurité,Je veux visualiser un tableau de bord web listant les dernières attaques avec leur horodatage, l'adresse IP source, le nom d'utilisateur et le mot de passe essayé,Afin de analyser rapidement les flux malveillants en temps réel.[Should Have] Statistiques globalesEn tant qu' administrateur de sécurité,Je veux voir des compteurs synthétiques (nombre total d'attaques et nombre d'IPs uniques) en haut du dashboard,Afin de évaluer d'un coup d'œil l'ampleur de la menace.[Could Have] Actualisation dynamiqueEn tant qu' administrateur de sécurité,Je veux que le dashboard se mette à jour automatiquement à intervalle régulier,Afin de laisser l'écran de monitoring ouvert en continu sans action manuelle.[Won't Have - MVP] Enregistrement complet des sessions (TTY logs)En tant qu' administrateur de sécurité,Je veux enregistrer et rejouer l'intégralité des commandes interactives tapées par l'attaquant dans un faux shell,Afin de étudier leurs scripts post-exploitation (prévu pour une version ultérieure).1.2 Maquette / Wireframe de l'Interface Principale+-------------------------------------------------------------------------+
| 🛡️ SSH HONEYPOT // DASHBOARD                        [ STATUT : ACTIF ]  |
+-------------------------------------------------------------------------+
|                                                                         |
|  +--------------------+  +--------------------+  +-------------------+  |
|  | TOTAL ATTAQUES     |  | IPS UNIQUES        |  | PAYS PRINCIPAL    |  |
|  |       142          |  |       28           |  |    CN / RU / US   |  |
|  +--------------------+  +--------------------+  +-------------------+  |
|                                                                         |
|  Dernières tentatives de connexion :                                    |
|  +-------------------------------------------------------------------+  |
|  | Timestamp          | IP Source     | User Testé  | Password       |  |
|  +--------------------+---------------+-------------+----------------+  |
|  | 2026-09-16 18:02   | 192.168.1.50  | root        | 123456         |  |
|  | 2026-09-16 18:00   | 45.33.32.156  | admin       | password       |  |
|  | 2026-09-16 17:55   | 185.220.101.5 | guest       | guest123       |  |
|  +-------------------------------------------------------------------+  |
|                                                                         |
+-------------------------------------------------------------------------+
2. Architecture SystèmeLe système repose sur une architecture découplée en trois couches : un cœur d'interception réseau en Python, une API REST de service, et une interface front-end pour la visualisation.  [ Attaquant / Bot ]
          │
          │ 1. Tentative de connexion SSH (Port 2222)
          ▼
  +───────────────────────────────────────────────────────────+
  |                   Honeypot Core (Python)                  |
  |                  (Paramiko / Mock Server)                 |
  +───────────────────────────────────────────────────────────+
          │
          │ 2. Capture des credentials (IP, User, Password)
          ▼
  +───────────────────────────────────────────────────────────+
  |                 Base de données (SQLite)                  |
  |                       (honeypot.db)                       |
  +───────────────────────────────────────────────────────────+
          ▲
          │ 3. Requête SQL (SELECT attacks)
          │
  +───────────────────────────────────────────────────────────+
  |                   Back-end API (Flask)                    |
  |              (Expose l'endpoint /api/attacks)             |
  +───────────────────────────────────────────────────────────+
          ▲
          │ 4. Requête HTTP GET (via CORS)
          │
  +───────────────────────────────────────────────────────────+
  |                 Front-end (Angular/React)                 |
  |                   (Dashboard / Table)                     |
  +───────────────────────────────────────────────────────────+
          ▲
          │ 5. Affichage dynamique en temps réel
          │
    [ Administrateur / Utilisateur ]
3. Composants, Classes et Conception de la Base de Données3.1 Description des ComposantsHoneypotServer (Python / Paramiko) : Écoute sur le port 2222, gère les bannières SSH, intercepte les tentatives d'authentification par mot de passe et déclenche l'écriture en base.DatabaseManager (database.py) : Encapsule les requêtes SQL vers SQLite (init_db, log_attack, get_all_attacks).API Flask (web_app.py) : Expose les routes REST pour communiquer les données du backend au front-end.Composants Front-end : En-tête de statut, cartes de statistiques (KPIs) et tableau dynamique de monitoring.3.2 Schéma de la Base de Données (SQLite)La base de données contient une unique table relationnelle nommée attacks :Table : attacksid : INTEGER (Clé primaire, auto-incrémentée)timestamp : DATETIME (Horodatage de l'attaque, défaut : CURRENT_TIMESTAMP)ip_address : TEXT (Adresse IP source de l'attaquant)username : TEXT (Nom d'utilisateur tenté)password : TEXT (Mot de passe tenté)4. Diagrammes de Séquence4.1 Capture et persistance d'une attaque SSH[ Attaquant ]          [ Honeypot Core (Paramiko) ]          [ Base de données (SQLite) ]
      │                              │                                    │
      │── 1. Connexion TCP (p. 2222) ────────────────>│                     │
      │                              │                                    │
      │── 2. Saisie User / Password ─>│                                    │
      │                              │── 3. log_attack(ip, user, pwd) ──>│
      │                              │                                    │
      │                              │    4. INSERT INTO attacks ... ─────┤
      │                              │<── 5. Confirmation d'écriture ─────│
      │<── 6. Fermeture / Rejet ─────│                                    │
4.2 Affichage et actualisation du Dashboard[ Administrateur ]      [ Front-end (SPA) ]           [ API Flask (web_app.py) ]      [ Base de données (SQLite) ]
       │                         │                               │                                 │
       │── 1. Ouvre le Dashboard ─>│                             │                                 │
       │                         │── 2. GET /api/attacks ───────>│                                 │
       │                         │                               │── 3. get_all_attacks() ────────>│
       │                         │                               │                                 │
       │                         │                               │    4. SELECT * FROM attacks ────┤
       │                         │                               │<── 5. Retourne la liste (JSON) ─│
       │                         │<── 6. Réponse HTTP 200 (JSON) ─│                                 │
       │<── 7. Rendu du tableau ─│                               │                                 │
5. Spécifications des API (Externes et Internes)5.1 API ExternesAPI de Géolocalisation IP (ex: ip-api.com ou ipapi.co) : Optionnelle, utilisée pour enrichir les adresses IP capturées avec le pays d'origine et le fournisseur d'accès.5.2 Endpoints de l'API Interne (Flask)Chemin URL (Path)Méthode HTTPFormat d'entréeFormat de sortie (JSON)Description/api/attacksGETAucunListe d'objets JSONRécupère la liste de toutes les tentatives d'authentification SSH./api/statsGETAucunObjet JSON synthétiqueFournit les indicateurs clés (total attaques, IPs uniques).Exemple de structure de sortie (JSON) pour /api/attacks :[
  {
    "id": 1,
    "timestamp": "2026-09-16 18:02:15",
    "ip_address": "192.168.1.50",
    "username": "root",
    "password": "123456"
  },
  {
    "id": 2,
    "timestamp": "2026-09-16 18:00:42",
    "ip_address": "45.33.32.156",
    "username": "admin",
    "password": "password"
  }
]
6. Stratégies SCM et QA6.1 Stratégie SCM (Software Configuration Management)Outil : Git et GitHub.Modèle de branches (Git Flow simplifié) :main : Code stable et validé pour la soutenance.development : Branche d'intégration des fonctionnalités.feature/* : Branches de travail isolées par composant (ex: feature/paramiko-honeypot, feature/flask-api).Validation : Commits atomiques réguliers, messages explicites et Pull Requests documentées.6.2 Stratégie QA (Quality Assurance)Types de tests :Tests unitaires : Validation des fonctions d'écriture en base et de la logique Paramiko.Tests d'intégration / API : Vérification des retours JSON des endpoints Flask.Tests fonctionnels : Connexion SSH manuelle locale (ssh root@localhost -p 2222) pour vérifier la remontée en temps réel.Outils : pytest pour les scripts Python, Postman / curl pour l'API.7. Justifications TechniquesPython & Paramiko : Choisi pour sa grande souplesse dans la manipulation des sockets réseau et son implémentation robuste du protocole SSH de bas niveau, permettant de simuler un serveur crédible en quelques lignes de code.Flask : Micro-framework Python léger, idéal pour monter rapidement une API REST propre sans la lourdeur d'usines à gaz comme Django, s'intégrant parfaitement avec SQLite.SQLite : Solution embarquée sans serveur additionnel requis, parfaitement adaptée à un MVP de taille modérée pour garantir une persistance rapide et autonome.Angular / React (Front-end SPA) : Offre une séparation claire des préoccupations, permettant d'afficher des tableaux dynamiques, réactifs et mis à jour de manière asynchrone pour un usage de type SOC (Security Operations Center).