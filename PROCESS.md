# Honeypot SSH Dashboard - PROCESS

## 0. Constitution de l'équipe et rôles
En tant que développeur solopreneur sur ce projet, j'occupe l'ensemble des rôles nécessaires au cycle de vie du logiciel :
- **Product Owner :** Définition du périmètre du MVP et priorisation des fonctionnalités.
- **Backend Developer (Python) :** Conception du serveur SSH, gestion de la persistance des données et de l'analyse des logs.
- **Frontend Developer (Angular) :** Développement de l'interface de visualisation et des composants interactifs du dashboard.
- **DevOps / Sécurité :** Configuration de l'environnement (Docker, WSL), sécurisation de l'infrastructure et déploiement.
- **Outils de travail :** Git/GitHub (gestion de projet et versioning), VS Code, Docker, Notion (documentation).

## 1. Brainstorming et Idées
Le processus de brainstorming a permis d'évaluer plusieurs types de honeypots pour répondre au besoin de traçabilité des attaques.

| Idée | Description | Statut |
| :--- | :--- | :--- |
| **Honeypot HTTP** | Capture des tentatives d'exploitation de vulnérabilités web. | Rejeté (trop large/complexe pour le MVP). |
| **Honeypot DB** | Simulation de bases de données vulnérables (ex: SQL Injection). | Rejeté (cibles trop spécifiques). |
| **Honeypot SSH** | Serveur simulant un accès SSH distant. | **Sélectionné** |

**Justification du choix (SSH) :**
- Forte pertinence face aux menaces réelles (attaques par force brute massives).
- Complexité technique idéale pour un projet certifiant.
- Données exploitables immédiatement (IP, pays, logs de connexion).

## 2. Sélection et définition du MVP

### Résumé du MVP
Le projet consiste en un **honeypot SSH** léger, capable d'intercepter des connexions, couplé à un **dashboard Angular** permettant de visualiser en temps réel les sources des attaques (géolocalisation, types d'attaques, fréquence).

### Pourquoi cette idée ?
Le SSH reste la cible prioritaire des attaquants automatisés. Ce projet permet d'allier cybersécurité (capture) et développement applicatif (dashboarding), offrant une vision concrète de la menace sur un réseau.

### Objectifs SMART (Fonctionnalités clés)
1. **Capturer les logs SSH :** Enregistrer 100% des tentatives de connexion (utilisateur, mot de passe, IP source, timestamp) dans une base de données MySQL/PostgreSQL.
2. **Géolocalisation :** Associer automatiquement 100% des IPs sources à leur pays via un service GeoIP.
3. **Visualisation :** Afficher un dashboard Angular mettant à jour les statistiques en temps réel avec au moins 3 graphiques différents (Top pays, Timeline des attaques, Type de login).

### Périmètre du projet
* **In-Scope (Inclus) :** Serveur SSH (Python/Paramiko), Backend API, Base de données, Dashboard Angular (Graphiques).
* **Out-of-Scope (Exclu) :** Simulation d'un OS complet (High-Interaction), système d'alerte complexe (mail/SMS), détection d'intrusions côté serveur réel.

### Risques et Atténuation
* **Risque :** Risque de sécurité lié à l'exposition d'un service réseau.
* **Atténuation :** Utilisation de Docker pour isoler le honeypot. Tests réalisés uniquement dans des environnements clos (WSL/réseau virtuel) avant tout déploiement.

---
*Projet réalisé dans le cadre de la certification RNCP5 - Holberton School.*