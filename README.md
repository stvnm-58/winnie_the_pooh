# winnie_the_pooh

mon-honeypot/
│
├── venv/                   <-- Ton environnement virtuel (créé ICI)
├── data/                   <-- Pour stocker la base de données SQLite
│   └── honeypot.db
│
├── src/                    <-- Le code source de l'application
│   ├── __init__.py
│   ├── honeypot.py         <-- Le script Paramiko (écoute SSH + capture)
│   ├── database.py         <-- Gestion de la base de données (SQLite)
│   └── web_app.py          <-- Le dashboard (Flask / FastAPI)
│
├── static/                 <-- Fichiers statiques pour le design du dashboard
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── charts.js       <-- Pour les graphiques (ex: Chart.js)
│
├── templates/              <-- Les fichiers HTML pour le dashboard
│   └── index.html
│
├── requirements.txt        <-- Liste des dépendances Python
└── README.md               <-- Documentation du projet