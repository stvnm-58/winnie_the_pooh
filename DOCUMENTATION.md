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