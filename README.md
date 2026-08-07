# Winnie the Pooh — Mon Honeypot

Description
-----------
Ce dépôt contient un projet honeypot conçu pour capturer des connexions SSH non autorisées et fournir un tableau de bord web pour visualiser les événements collectés. Le projet combine un composant d'écoute SSH (capture) avec une interface web (dashboard).

Principales fonctionnalités
---------------------------
- Capture et journalisation des connexions SSH
- Stockage local des événements dans `data/` (SQLite)
- Dashboard web pour visualiser les attaques (templates + fichiers statiques)

Structure du dépôt
------------------
- `.git/` et `.gitignore` : gestion de version
- `venv/` : environnement virtuel (ne pas committer)
- `data/` : base de données et fichiers générés (`honeypot.db` ou équivalent)
- `src/` : code source principal
	- `honeypot.py` : logic d'écoute et capture (ex: Paramiko)
	- `database.py` : helpers pour la persistance (SQLite)
	- `web_app.py` : application web (Flask / FastAPI)
- `static/` : fichiers statiques du dashboard (CSS, JS)
- `templates/` : templates HTML du dashboard
- `requirements/` ou `requirements.txt` : dépendances Python

Prérequis
---------
- Python 3.8+ installé
- `pip` pour installer les dépendances
- (Recommandé) Créer un environnement virtuel pour isoler les dépendances

Installation rapide
------------------
1. Créer et activer un environnement virtuel :

	 - Unix / macOS:

		 ```bash
		 python3 -m venv venv
		 source venv/bin/activate
		 ```

	 - Windows (PowerShell):

		 ```powershell
		 python -m venv venv
		 .\venv\Scripts\Activate.ps1
		 ```

2. Installer les dépendances :

	 - Si `requirements.txt` est à la racine :

		 ```bash
		 pip install -r requirements.txt
		 ```

	 - Si les requirements sont dans le dossier `requirements/` :

		 ```bash
		 pip install -r requirements/requirements.txt
		 ```

Configuration
-------------
- Fichier de base de données attendu : `data/honeypot.db` (ou réglable dans `src/database.py`)
- Variables d'environnement possibles :
	- `FLASK_ENV` / `APP_ENV` pour le mode de l'application web
	- `DATABASE_URL` si vous souhaitez pointer vers une autre DB

Usage
-----
- Lancer le capteur SSH (exemple) :

	```bash
	python src/honeypot.py
	```

- Lancer le dashboard web (exemple Flask) :

	```bash
	# depuis la racine du projet
	export FLASK_APP=src.web_app
	flask run --host=0.0.0.0 --port=5000
	```

	(Sous Windows PowerShell, remplacez `export` par `setx` ou utilisez la syntaxe appropriée)

Tests
-----
- Si des tests sont présents, lancez :

	```bash
	pytest
	```

Bonnes pratiques
----------------
- Ne commitez pas `venv/` ni `data/` (ajoutés normalement à `.gitignore`)
- Sécurisez l'accès au dashboard et à la base de données si vous exposez l'application

Contribuer
----------
- Forkez le dépôt, créez une branche feature, puis ouvrez une pull request.
- Documentez tout nouveau comportement et ajoutez des tests lorsque possible.

Licence
-------
Aucune licence spécifiée. Ajouter un fichier `LICENSE` si vous souhaitez en définir une (MIT recommandée pour les prototypes).

Contact
-------
Pour questions ou contributions : ouvre une issue ou contacte l'auteur du dépôt.

Remarques
---------
Ce README a été rédigé automatiquement à partir de la structure du dossier. Adaptez les commandes et chemins selon vos scripts réels (par ex. si l'app web s'appelle différemment ou si les dépendances sont rangées autrement).
