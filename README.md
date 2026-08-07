# Winnie the Pooh — My Honeypot

Description
-----------
This repository contains a honeypot project designed to capture unauthorized SSH connections and provide a web dashboard to visualize collected events. The project combines an SSH listener/capture component with a web interface (dashboard).

Key Features
------------
- Capture and logging of SSH connection attempts
- Local storage of events in `data/` (SQLite)
- Web dashboard to visualize attacks (templates + static assets)

Repository Structure
--------------------
- `.git/` and `.gitignore`: version control
- `venv/`: virtual environment (do not commit)
- `data/`: database and generated files (e.g. `honeypot.db`)
- `src/`: main source code
  - `honeypot.py`: listener/capture logic (e.g. using Paramiko)
  - `database.py`: persistence helpers (SQLite)
  - `web_app.py`: web application (Flask / FastAPI)
- `static/`: dashboard static files (CSS, JS)
- `templates/`: dashboard HTML templates
- `requirements/` or `requirements.txt`: Python dependencies

Requirements
------------
- Python 3.8+ installed
- `pip` to install dependencies
- (Recommended) Create a virtual environment to isolate dependencies

Quick Setup
-----------
1. Create and activate a virtual environment:

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

2. Install dependencies:

   - If `requirements.txt` is at the project root:

     ```bash
     pip install -r requirements.txt
     ```

   - If dependencies are in the `requirements/` folder:

     ```bash
     pip install -r requirements/requirements.txt
     ```

Configuration
-------------
- Expected database file: `data/honeypot.db` (configurable in `src/database.py`)
- Environment variables you may use:
  - `FLASK_ENV` / `APP_ENV` for the web app mode
  - `DATABASE_URL` if you want to point to a different database

Usage
-----
- Start the SSH listener (example):

  ```bash
  python src/honeypot.py
  ```

- Start the web dashboard (Flask example):

  ```bash
  # from the project root
  export FLASK_APP=src.web_app
  flask run --host=0.0.0.0 --port=5000
  ```

  (On Windows PowerShell, replace `export` with the appropriate command or set the environment variable before running Flask.)

Tests
-----
- If tests are available, run:

  ```bash
  pytest
  ```

Best Practices
--------------
- Do not commit `venv/` or `data/` (these should be in `.gitignore`)
- Secure access to the dashboard and the database if you expose the application publicly

Contributing
------------
- Fork the repository, create a feature branch, and open a pull request.
- Document new behavior and add tests when possible.

License
-------
No license specified. Add a `LICENSE` file if you want to define one (MIT is commonly used for prototypes).

Contact
-------
For questions or contributions: open an issue or contact the repository owner.

Notes
-----
This README was generated from the repository structure. Adjust commands and paths to match your actual scripts (for example, if the web app module has a different name or dependencies are organized differently).

