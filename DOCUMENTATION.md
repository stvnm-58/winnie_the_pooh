# Dossier de Conception : Honeypot SSH Modulaire & Dashboard de Surveillance
*Projet de Fin d'Études (RNCP5)*

---

## 1. User Stories et Maquettes

### 1.1 Liste des User Stories (Priorisées MoSCoW)

* **[Must Have] Capture des connexions SSH**
  * *As a* administrateur de sécurité,
  * *I want* que le honeypot écoute sur un port dédié et intercepte les tentatives de connexion SSH,
  * *So that* je puisse capturer les identifiants (utilisateurs et mots de passe) testés par les bots ou attaquants.

* **[Must Have] Stockage persistant**
  * *As a* administrateur de sécurité,
  * *I want* que chaque tentative d'attaque capturée soit enregistrée de manière permanente dans une base de données,
  * *So that* l'historique ne soit pas perdu lors du redémarrage des services.

* **[Must Have] Affichage du tableau de bord**
  * *As a* administrateur de sécurité,
  * *I want* visualiser un tableau de bord web listant les dernières attaques avec leur horodatage, l'adresse IP source, le nom d'utilisateur et le mot de passe essayé,
  * *So that* je puisse analyser rapidement les flux malveillants en temps réel.

* **[Should Have] Statistiques globales**
  * *As a* administrateur de sécurité,
  * *I want* voir des compteurs synthétiques (nombre total d'attaques et nombre d'IPs uniques) en haut du dashboard,
  * *So that* je puisse évaluer d'un coup d'œil l'ampleur de la menace.

* **[Could Have] Actualisation dynamique**
  * *As a* administrateur de sécurité,
  * *I want* que le dashboard se mette à jour automatiquement à intervalle régulier sans action manuelle,
  * *So that* je puisse laisser l'écran de monitoring ouvert en continu.

* **[Won't Have - MVP] Enregistrement complet des sessions (TTY logs)**
  * *As a* administrateur de sécurité,
  * *I want* enregistrer et rejouer l'intégralité des commandes interactives tapées par l'attaquant dans un faux shell,
  * *So that* je puisse étudier leurs scripts post-exploitation (prévu pour une version ultérieure).

### 1.2 Maquette / Wireframe de l'Interface Principale

```text
+-------------------------------------------------------------------------+
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
```

---

## 2. Architecture Système 
```text
[ Attaquant / Bot ]
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
```
---

## 3. Composants, Classes et Conception de la Base de Données

### 3.1 Description des Composants

    HoneypotServer (Python / Paramiko) : Écoute sur le port 2222, gère les bannières SSH, intercepte les tentatives d'authentification par mot de passe et déclenche l'écriture en base.

    DatabaseManager (database.py) : Encapsule les requêtes SQL vers SQLite (init_db, log_attack, get_all_attacks).

    API Flask (web_app.py) : Expose les routes REST pour communiquer les données du backend au front-end.

    Composants Front-end : En-tête de statut, cartes de statistiques (KPIs) et tableau dynamique de monitoring.

### 3.2 Schéma de la Base de Données (SQLite)

La base de données contient une unique table relationnelle nommée attacks :

    Table : attacks

        id : INTEGER (Clé primaire, auto-incrémentée)

        timestamp : DATETIME (Horodatage de l'attaque, défaut : CURRENT_TIMESTAMP)

        ip_address : TEXT (Adresse IP source de l'attaquant)

        username : TEXT (Nom d'utilisateur tenté)

        password : TEXT (Mot de passe tenté)

---

## 4. Diagrammes de Séquence

### 4.1 Capture et persistance d'une attaque SSH

```text
[ Attaquant ]          [ Honeypot Core (Paramiko) ]          [ Base de données (SQLite) ]
      │                              │                                    │
      │─ 1. Connexion TCP (p. 2222) >│                                    │
      │                              │                                    │
      │── 2. Saisie User / Password >│                                    │
      │                              │── 3. log_attack(ip, user, pwd) ──> │
      │                              │                                    │
      │                              │    4. INSERT INTO attacks ... ─────┤
      │                              │<── 5. Confirmation d'écriture ─────│
      │<── 6. Fermeture / Rejet ─────│                                    │
      │    (Authentification échouée)│                                    │

```

### 4.2 Affichage et actualisation du Dashboard

```text
[ Administrateur ]      [ Front-end (SPA) ]           [ API Flask (web_app.py) ]      [ Base de données (SQLite) ]
       │                         │                               │                                 │
       │─ 1. Ouvre le Dashboard >│                               │                                 │
       │                         │── 2. GET /api/attacks ───────>│                                 │
       │                         │                               │── 3. get_all_attacks() ────────>│
       │                         │                               │                                 │
       │                         │                               │    4. SELECT * FROM attacks ────┤
       │                         │                               │<── 5. Retourne la liste (JSON) ─│
       │                         │<─ 6. Réponse HTTP 200 (JSON) ─│                                 │
       │<── 7. Rendu du tableau ─│                               │                                 │
```

---

## 5. Spécifications des API

### 5.1 API Externes
* **API de Géolocalisation IP (ex: *ipapi.co*)** : Utilisée optionnellement pour enrichir les logs IP avec le pays d'origine de l'attaque.

### 5.2 Endpoints de l'API Interne (Flask)
```text
| Chemin URL (`Path`) | Méthode HTTP | Format d'entrée | Format de sortie | Description |
| :--- | :--- | :--- | :--- | :--- |
| `/api/attacks` | `GET` | Aucun | JSON (Liste d'objets) | Récupère toutes les tentatives d'authentification SSH. |
| `/api/stats` | `GET` | Aucun | JSON (Objet) | Fournit les indicateurs clés (total attaques, IPs uniques). |
```
---

## 6. Stratégies SCM et QA

### 6.1 Stratégie SCM (Software Configuration Management)
* **Outil :** Git & GitHub.
* **Branches :** `main` (production stable), `development` (intégration), et `feature/*` (fonctionnalités isolées).
* **Processus :** Commits atomiques réguliers, validation par Pull Requests (PR) avant fusion.

### 6.2 Stratégie QA (Quality Assurance)
* **Types de tests :**
  * *Tests unitaires :* Validation des fonctions d'insertion SQL et de l'interception Paramiko.
  * *Tests d'intégration / API :* Vérification des endpoints Flask.
  * *Tests fonctionnels :* Simulation manuelle d'une attaque avec un client SSH local (`ssh root@localhost -p 2222`).
* **Outils :** `pytest` pour le back-end, Postman / `curl` pour l'API.

---

## 7. Justifications Techniques
* **Python & Paramiko :** Choisi pour sa rapidité de développement, sa flexibilité dans la manipulation des sockets réseau et son module robuste d'émulation de protocole SSH.
* **Flask :** Léger, minimaliste et idéal pour monter rapidement une API REST sans la lourdeur d'un framework comme Django.
* **SQLite :** Solution embarquée parfaite pour un MVP, évitant la configuration d'un serveur de base de données externe tout en garantissant la persistance des données.
* **Angular / SPA :** Choisi pour structurer proprement le front-end du dashboard de monitoring avec une architecture modulaire et rigoureuse.