# Planning du Projet : Honeypot SSH & Dashboard

Ce document présente la roadmap globale du projet, structurée en phases logiques pour assurer un développement fluide, du serveur de capture jusqu'au dashboard de visualisation.

## Calendrier des phases (High-Level Plan)

| Phase | Nom de la phase | Objectifs principaux | Durée estimée |
| :--- | :--- | :--- | :--- |
| **1** | **Setup & Infrastructure** | Initialisation du repo, config Docker, setup Python/Angular. | 3 jours |
| **2** | **Core Honeypot (Back)** | Développement du serveur SSH, logs, persistance des données. | 7 jours |
| **3** | **API & Backend** | Création de l'API pour exposer les données du honeypot. | 5 jours |
| **4** | **Dashboard (Front)** | Développement Angular, connexion API, intégration des graphiques. | 10 jours |
| **5** | **Test, Sécurité & Doc** | Tests de simulation, finalisation, rédaction de la doc technique. | 5 jours |

---

## Détail des phases

### Phase 1 : Setup & Infrastructure (3 jours)
*   Initialisation du dépôt GitHub.
*   Configuration de l'environnement de développement (VS Code, WSL).
*   Mise en place des fichiers de configuration Docker pour assurer l'isolation.

### Phase 2 : Core Honeypot (Python) (7 jours)
*   Implémentation du serveur SSH en utilisant la bibliothèque `Paramiko`.
*   Gestion des connexions entrantes (authentification factice pour capturer les tentatives).
*   Stockage des logs bruts : adresse IP, timestamp, utilisateur, mot de passe, version SSH.

### Phase 3 : API Backend (5 jours)
*   Développement d'une API REST pour interroger la base de données de logs.
*   Intégration d'un service de géolocalisation pour convertir les IPs en données géographiques (Pays/Ville).
*   Création des endpoints nécessaires : liste des attaques, statistiques agrégées.

### Phase 4 : Dashboard (Angular) (10 jours)
*   Initialisation de l'application Angular.
*   Intégration d'une bibliothèque de graphiques pour visualiser les attaques.
*   Mise en place de l'interface utilisateur pour consulter la traçabilité des attaques.

### Phase 5 : Tests & Finalisation (5 jours)
*   Simulation d'attaques (Brute Force) pour valider la capture et l'affichage.
*   Nettoyage du code et finalisation de la documentation technique.