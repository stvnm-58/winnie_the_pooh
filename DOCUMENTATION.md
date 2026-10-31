# Dossier de Conception : Honeypot SSH Modulaire & Dashboard de Surveillance

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

* **[Should Have] Changement du port d'écoute**
  * *As a* administrateur de sécurité,
  * *I want* changer le port du honeypot depuis le dashboard,
  * *So that* je puisse déplacer son port d'écoute sans redémarrer manuellement les services.

* **[Should Have] Plusieurs honeypots simultanés**
  * *As a* administrateur de sécurité,
  * *I want* déployer plusieurs honeypots sur des ports distincts et les arrêter individuellement,
  * *So that* je puisse surveiller plusieurs points d'entrée SSH en parallèle.

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
          │ 1. Tentative de connexion SSH (port configurable, 2222 par défaut)
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
  |                 Front-end (React)                         |
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

    HoneypotServer (Python / Paramiko) : Chaque processus écoute sur son propre port SSH (2222 par défaut pour l'instance principale). Le dashboard permet de déployer plusieurs instances sur des ports distincts et de les arrêter individuellement. Les tentatives capturées sont enregistrées avec le port qui les a reçues.

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
* **API de Géolocalisation IP (ex: *ipapi.co*)** : L'enrichissement est effectué en arrière-plan après l'enregistrement de la tentative. Les résultats sont mis en cache pendant 24 heures (5 minutes pour les résultats inconnus) ; les adresses non publiques ne sont pas envoyées au service externe.

### 5.2 Endpoints de l'API Interne (Flask)
```text
| Chemin URL (`Path`) | Méthode HTTP | Paramètres de requête | Format de sortie | Description |
| :--- | :--- | :--- | :--- | :--- |
| `/api/attacks` | `GET` | `limit` (1-500), `before_id` ou `after_id` | JSON (Liste d'objets) | Récupère une page de tentatives. Sans curseur, retourne les plus récents IDs. |
| `/api/commands` | `GET` | `limit` (1-500), `before_id` ou `after_id` | JSON (Liste d'objets) | Récupère une page de commandes. |
| `/api/country-updates/latest` | `GET` | Aucun | JSON (`id`) | Retourne le curseur de départ des mises à jour de géolocalisation. |
| `/api/country-updates` | `GET` | `limit` (1-500), `after_id` | JSON (Liste d'objets) | Récupère les pays ajoutés après la capture, sans recharger les attaques. |
| `/api/stats` | `GET` | Aucun | JSON (Objet) | Fournit les indicateurs clés (total attaques, IPs uniques). |
```

Les endpoints d'attaques et de commandes limitent chaque réponse à 500 entrées par défaut. Pour charger les plus anciennes, réutiliser le plus petit `id` de la page dans `before_id`; pour obtenir les entrées ajoutées depuis un curseur, utiliser `after_id`. Les mises à jour GeoIP sont diffusées séparément afin que l'enrichissement asynchrone apparaisse sans renvoyer l'historique. Les nouveaux horodatages sont stockés en UTC avec le suffixe `Z`. Le honeypot conserve les données récentes dans SQLite avec WAL et archive les données de plus de 30 jours par lots. Seule l'instance principale effectue l'archivage ; les instances secondaires lancées par le dashboard utilisent l'option interne `--no-archive`.

Le port principal est configuré dans `server/data/config.json`. Le listener SSH, l'API et la gestion du pare-feu utilisent ce même fichier ; les bases SQLite et l'état des IP bannies sont également conservés dans `server/data/`.
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
* **Outils :** `unittest` (bibliothèque standard Python) pour les tests backend, Postman / `curl` pour l'API.

Depuis le dossier `server`, lancer les tests automatisés avec :

```bash
python -m unittest discover -s tests -v
```

Les tests utilisent des bases SQLite temporaires et ne modifient pas les données du honeypot.

---

## 7. Justifications Techniques
* **Python & Paramiko :** Choisi pour sa rapidité de développement, sa flexibilité dans la manipulation des sockets réseau et son module robuste d'émulation de protocole SSH.
* **Flask :** Léger, minimaliste et idéal pour monter rapidement une API REST sans la lourdeur d'un framework comme Django.
* **SQLite :** Solution embarquée parfaite pour un MVP, évitant la configuration d'un serveur de base de données externe tout en garantissant la persistance des données.
* **REACT :** Choisi pour structurer proprement le front-end du dashboard de monitoring avec une architecture modulaire et rigoureuse.