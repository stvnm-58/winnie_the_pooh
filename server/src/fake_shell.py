# src/fake_shell.py
import os
from database import log_command  # <-- Import de la fonction de log BDD

def handle_fake_shell(channel, client_ip):  # <-- Réception de l'IP du client
    try:
        # Système de fichiers virtuel simulant une machine Linux compromise
        virtual_fs = {
            "/root": ["config.json", "backups.zip", "root.txt", ".ssh"],
            "/root/.ssh": ["authorized_keys", "id_rsa"],
            "/var/log": ["auth.log", "syslog", "nginx"],
            "/var/www/html": ["index.html", "admin.php", "config.php"],
            "/tmp": ["exploit", "privesc.sh"]
        }
        
        # Dictionnaire pour stocker le contenu réel des fichiers (statiques et dynamiques)
        file_contents = {
            "root.txt": "FLAG{winnie_the_pooh_honey_jar_2026}\r\n",
            "config.json": '{\n    "db_host": "127.0.0.1",\n    "db_user": "admin",\n    "secret_token": "a8f5c3e921b"\n}\r\n',
            "auth.log": "Sep 30 12:00:10 ubuntu sshd[8412]: Accepted password for root from 10.0.2.15 port 45123 ssh2\r\nSep 30 12:05:22 ubuntu sshd[8520]: Failed password for invalid user admin from 192.168.1.50 port 51200 ssh2\r\n",
            "id_rsa": "-----BEGIN OPENSSH PRIVATE KEY-----\r\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlw==\r\n-----END OPENSSH PRIVATE KEY-----\r\n"
        }
        
        current_dir = "/root"

        channel.send(b"Welcome to Ubuntu 22.04.3 LTS (GNU/Linux 5.15.0-88-generic x86_64)\r\n\r\n")
        channel.send(f"root@ubuntu:{current_dir}# ".encode())
        
        buffer = b""
        while True:
            data = channel.recv(1024)
            # Arrête la boucle si le client ferme la connexion
            if not data:
                break
            
            for byte in data:
                char = bytes([byte])
                
                # Intercepte la touche Backspace pour effacer un caractère
                if char in (b'\x7f', b'\b'):
                    # Vérifie qu'il reste des caractères à supprimer dans le buffer
                    if len(buffer) > 0:
                        buffer = buffer[:-1]
                        channel.send(b'\b \b')
                
                # Intercepte la tabulation pour déclencher l'autocomplétion
                elif char == b'\t':
                    cmd_str = buffer.decode("utf-8", errors="ignore")
                    parts = cmd_str.split(" ")
                    
                    # Vérifie si le tampon contient des éléments à analyser
                    if len(parts) > 0:
                        prefix = parts[-1]
                        choices = virtual_fs.get(current_dir, [])
                        
                        # Élargit l'autocomplétion aux dossiers globaux si la commande est cd
                        if parts[0] == "cd" and len(parts) == 2:
                            choices = [os.path.basename(d) for d in virtual_fs.keys() if d.startswith("/")]
                        
                        matches = [c for c in choices if c.startswith(prefix)]
                        
                        # Complète automatiquement s'il n'y a qu'une seule correspondance
                        if len(matches) == 1:
                            completion = matches[0][len(prefix):]
                            buffer += completion.encode("utf-8")
                            channel.send(completion.encode("utf-8"))
                        # Affiche les choix possibles s'il y a plusieurs correspondances
                        elif len(matches) > 1:
                            channel.send(b"\r\n" + "  ".join(matches).encode("utf-8") + b"\r\n")
                            channel.send(f"root@ubuntu:{current_dir}# {cmd_str}".encode("utf-8"))

                # Intercepte la touche Entrée pour valider et exécuter la commande
                elif char in (b'\n', b'\r'):
                    channel.send(b"\r\n")
                    cmd = buffer.decode("utf-8", errors="ignore").strip()
                    print(f"[CMD] Commande interceptée à {current_dir} : {cmd}")
                    
                    # Enregistrement en base de données si la commande n'est pas vide
                    if cmd != "":
                        log_command(client_ip, cmd, current_dir)
                    
                    # Permet à l'attaquant de quitter la session
                    if cmd.lower() in ("exit", "quit"):
                        channel.send(b"logout\r\n")
                        return
                        
                    # Simule une version de noyau Linux
                    elif cmd.startswith("uname"):
                        channel.send(b"Linux ubuntu 5.15.0-88-generic #98-Ubuntu SMP Mon Oct 2 15:18:56 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux\r\n")
                        
                    # Simule l'identité root
                    elif cmd.startswith("id"):
                        channel.send(b"uid=0(root) gid=0(root) groups=0(root)\r\n")
                        
                    # Renvoie l'utilisateur courant
                    elif cmd.startswith("whoami"):
                        channel.send(b"root\r\n")
                        
                    # Affiche le répertoire courant
                    elif cmd.startswith("pwd"):
                        channel.send(f"{current_dir}\r\n".encode())
                        
                    # Simule la commande ls avec gestion des flags -l et -a
                    elif cmd.startswith("ls"):
                        parts = cmd.split()
                        flags = ""
                        for p in parts[1:]:
                            if p.startswith("-"):
                                flags += p[1:]
                        
                        long_format = 'l' in flags
                        show_all = 'a' in flags
                        
                        files = virtual_fs.get(current_dir, [])
                        
                        # Filtre les fichiers cachés selon la présence du flag -a
                        if not show_all:
                            filtered_files = [f for f in files if not f.startswith('.')]
                        else:
                            filtered_files = ['.', '..'] + [f for f in files if f != '.' and f != '..']
                        
                        # Affiche le format long ou simple selon le flag -l
                        if long_format:
                            channel.send(b"total 28\r\n")
                            for f in filtered_files:
                                full_path = os.path.normpath(os.path.join(current_dir, f)).replace("\\", "/")
                                is_dir = full_path in virtual_fs or f in ('.', '..')
                                
                                # Attribue des permissions spécifiques selon le type d'élément
                                if is_dir:
                                    perms = "drwx------" if f in (".ssh", ".") else "drwxr-xr-x"
                                    links = "2"
                                    size = "4096"
                                else:
                                    perms = "-rw-r--r--"
                                    links = "1"
                                    size = "2048" if f == "backups.zip" else "220"
                                    
                                line = f"{perms} {links} root root {size:>4} Sep 30 12:00 {f}\r\n"
                                channel.send(line.encode("utf-8"))
                        else:
                            channel.send("  ".join(filtered_files).encode("utf-8") + b"\r\n")
                        
                    # Simule la création d'un dossier virtuel
                    elif cmd.startswith("mkdir "):
                        target = cmd.split(" ", 1)[1].strip()
                        new_dir = os.path.normpath(target if target.startswith("/") else os.path.join(current_dir, target)).replace("\\", "/")
                        
                        # Vérifie si le répertoire n'existe pas déjà
                        if new_dir not in virtual_fs:
                            virtual_fs[new_dir] = []
                            parent_dir = os.path.dirname(new_dir)
                            # Corrige le dossier parent si vide
                            if parent_dir == "": parent_dir = "/"
                            folder_name = os.path.basename(new_dir)
                            
                            parent_files = virtual_fs.setdefault(parent_dir, [])
                            # Ajoute le dossier aux fichiers du parent s'il n'y est pas
                            if folder_name not in parent_files:
                                parent_files.append(folder_name)
                        else:
                            channel.send(f"mkdir: cannot create directory '{target}': File exists\r\n".encode())

                    # Simule la création d'un fichier vide (touch)
                    elif cmd.startswith("touch "):
                        target = cmd.split(" ", 1)[1].strip()
                        current_files = virtual_fs.setdefault(current_dir, [])
                        if target not in current_files:
                            current_files.append(target)
                        # Un fichier créé avec touch est vide par défaut
                        file_contents[target] = ""

                    # Gestion de la commande echo et écriture dans des fichiers (> ou >>)
                    elif cmd.startswith("echo "):
                        if ">>" in cmd:
                            parts = cmd.split(">>")
                            content_part = parts[0].replace("echo", "").strip().strip('"').strip("'")
                            target_file = parts[1].strip()
                            
                            current_files = virtual_fs.setdefault(current_dir, [])
                            if target_file not in current_files:
                                current_files.append(target_file)
                            
                            # Ajoute le contenu à la suite (append)
                            existing_content = file_contents.get(target_file, "")
                            file_contents[target_file] = existing_content + content_part + "\r\n"
                            
                        elif ">" in cmd:
                            parts = cmd.split(">")
                            content_part = parts[0].replace("echo", "").strip().strip('"').strip("'")
                            target_file = parts[1].strip()
                            
                            current_files = virtual_fs.setdefault(current_dir, [])
                            if target_file not in current_files:
                                current_files.append(target_file)
                            
                            # Écrase ou définit le contenu du fichier
                            file_contents[target_file] = content_part + "\r\n"
                        else:
                            text_to_echo = cmd[5:].strip().strip('"').strip("'")
                            channel.send(f"{text_to_echo}\r\n".encode("utf-8"))

                    # Simule la lecture de fichier avec cat (et prise en compte optionnelle d'un pipe grep)
                    elif cmd.startswith("cat "):
                        parts = cmd.split("|")
                        cat_part = parts[0].strip()
                        grep_pattern = parts[1].strip().replace("grep ", "").strip('"').strip("'") if len(parts) > 1 else None

                        target = cat_part.split(" ", 1)[1].strip()
                        files_in_dir = virtual_fs.get(current_dir, [])
                        target_path = os.path.normpath(os.path.join(current_dir, target)).replace("\\", "/")
                        
                        # Vérifie si la cible est un fichier valide existant
                        if target in files_in_dir and target_path not in virtual_fs:
                            content = file_contents.get(target, "")
                            
                            # Si un grep est présent dans la commande
                            if grep_pattern:
                                lines = content.splitlines()
                                filtered_lines = [l for l in lines if grep_pattern.lower() in l.lower()]
                                content = "\r\n".join(filtered_lines) + ("\r\n" if filtered_lines else "")

                            channel.send(content.encode("utf-8"))
                        # Gère le cas où la cible est un dossier
                        elif target_path in virtual_fs:
                            channel.send(f"cat: {target}: Is a directory\r\n".encode())
                        # Gère le cas où le fichier n'existe pas
                        else:
                            channel.send(f"cat: {target}: No such file or directory\r\n".encode())

                    # Gère le changement de répertoire avec cd et un argument
                    elif cmd.startswith("cd "):
                        target = cmd.split(" ", 1)[1].strip()
                        # Distingue chemin absolu et relatif
                        if target.startswith("/"):
                            new_dir = os.path.normpath(target)
                        else:
                            new_dir = os.path.normpath(os.path.join(current_dir, target))
                        
                        new_dir = new_dir.replace("\\", "/")
                        
                        # Vérifie si le dossier de destination existe
                        if new_dir in virtual_fs:
                            current_dir = new_dir
                        else:
                            channel.send(f"cd: {target}: No such file or directory\r\n".encode())
                                
                    # Gère la commande cd tapée seule (retour à /root)
                    elif cmd == "cd":
                        current_dir = "/root"
                        
                    # Ignore les lignes vides
                    elif cmd == "":
                        pass
                        
                    # Gère les commandes non reconnues
                    else:
                        channel.send(f"bash: {cmd}: command not found\r\n".encode())
                    
                    channel.send(f"root@ubuntu:{current_dir}# ".encode())
                    buffer = b""
                
                # Accumule les caractères normaux saisis dans le buffer et envoie l'écho
                else:
                    buffer += char
                    channel.send(char)
                    
    except Exception as e:
        print(f"[-] Erreur dans le faux shell : {e}")
    finally:
        channel.close()