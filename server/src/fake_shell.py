# src/fake_shell.py
import os

def handle_fake_shell(channel):
    try:
        # Système de fichiers virtuel simulant une machine Linux compromise
        virtual_fs = {
            "/root": ["config.json", "backups.zip", "root.txt", ".ssh"],
            "/root/.ssh": ["authorized_keys", "id_rsa"],
            "/var/log": ["auth.log", "syslog", "nginx"],
            "/var/www/html": ["index.html", "admin.php", "config.php"],
            "/tmp": ["exploit", "privesc.sh"]
        }
        
        current_dir = "/root"

        channel.send(b"Welcome to Ubuntu 22.04.3 LTS (GNU/Linux 5.15.0-88-generic x86_64)\r\n\r\n")
        channel.send(f"root@ubuntu:{current_dir}# ".encode())
        
        buffer = b""
        while True:
            data = channel.recv(1024)
            if not data:
                break
            
            for byte in data:
                char = bytes([byte])
                
                # Gestion du Backspace
                if char in (b'\x7f', b'\b'):
                    if len(buffer) > 0:
                        buffer = buffer[:-1]
                        channel.send(b'\b \b')
                
                # Gestion de la touche Tabulation (Autocomplétion)
                elif char == b'\t':
                    cmd_str = buffer.decode("utf-8", errors="ignore")
                    parts = cmd_str.split(" ")
                    
                    if len(parts) > 0:
                        prefix = parts[-1]
                        choices = virtual_fs.get(current_dir, [])
                        
                        if parts[0] == "cd" and len(parts) == 2:
                            choices = [os.path.basename(d) for d in virtual_fs.keys() if d.startswith("/")]
                        
                        matches = [c for c in choices if c.startswith(prefix)]
                        
                        if len(matches) == 1:
                            completion = matches[0][len(prefix):]
                            buffer += completion.encode("utf-8")
                            channel.send(completion.encode("utf-8"))
                        elif len(matches) > 1:
                            channel.send(b"\r\n" + "  ".join(matches).encode("utf-8") + b"\r\n")
                            channel.send(f"root@ubuntu:{current_dir}# {cmd_str}".encode("utf-8"))

                # Gestion de la touche Entrée
                elif char in (b'\n', b'\r'):
                    channel.send(b"\r\n")
                    cmd = buffer.decode("utf-8", errors="ignore").strip()
                    print(f"[CMD] Commande interceptée à {current_dir} : {cmd}")
                    
                    if cmd.lower() in ("exit", "quit"):
                        channel.send(b"logout\r\n")
                        return
                        
                    elif cmd.startswith("uname"):
                        channel.send(b"Linux ubuntu 5.15.0-88-generic #98-Ubuntu SMP Mon Oct 2 15:18:56 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux\r\n")
                        
                    elif cmd.startswith("id"):
                        channel.send(b"uid=0(root) gid=0(root) groups=0(root)\r\n")
                        
                    elif cmd.startswith("whoami"):
                        channel.send(b"root\r\n")
                        
                    elif cmd.startswith("pwd"):
                        channel.send(f"{current_dir}\r\n".encode())
                        
                    elif cmd.startswith("ls"):
                        parts = cmd.split()
                        flags = ""
                        for p in parts[1:]:
                            if p.startswith("-"):
                                flags += p[1:]
                        
                        long_format = 'l' in flags
                        show_all = 'a' in flags
                        
                        files = virtual_fs.get(current_dir, [])
                        
                        # Gestion des fichiers cachés avec -a ou -la
                        if not show_all:
                            filtered_files = [f for f in files if not f.startswith('.')]
                        else:
                            filtered_files = ['.', '..'] + [f for f in files if f != '.' and f != '..']
                        
                        if long_format:
                            channel.send(b"total 28\r\n")
                            for f in filtered_files:
                                full_path = os.path.normpath(os.path.join(current_dir, f)).replace("\\", "/")
                                is_dir = full_path in virtual_fs or f in ('.', '..')
                                
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
                        
                    elif cmd.startswith("mkdir "):
                        target = cmd.split(" ", 1)[1].strip()
                        new_dir = os.path.normpath(target if target.startswith("/") else os.path.join(current_dir, target)).replace("\\", "/")
                        
                        if new_dir not in virtual_fs:
                            virtual_fs[new_dir] = []
                            parent_dir = os.path.dirname(new_dir)
                            if parent_dir == "": parent_dir = "/"
                            folder_name = os.path.basename(new_dir)
                            
                            parent_files = virtual_fs.setdefault(parent_dir, [])
                            if folder_name not in parent_files:
                                parent_files.append(folder_name)
                        else:
                            channel.send(f"mkdir: cannot create directory '{target}': File exists\r\n".encode())

                    elif cmd.startswith("touch "):
                        target = cmd.split(" ", 1)[1].strip()
                        current_files = virtual_fs.setdefault(current_dir, [])
                        if target not in current_files:
                            current_files.append(target)

                    elif cmd.startswith("cat "):
                        target = cmd.split(" ", 1)[1].strip()
                        files_in_dir = virtual_fs.get(current_dir, [])
                        target_path = os.path.normpath(os.path.join(current_dir, target)).replace("\\", "/")
                        
                        if target in files_in_dir and target_path not in virtual_fs:
                            mock_contents = {
                                "root.txt": "FLAG{winnie_the_pooh_honey_jar_2026}\r\n",
                                "config.json": '{\n    "db_host": "127.0.0.1",\n    "db_user": "admin",\n    "secret_token": "a8f5c3e921b"\n}\r\n',
                                "auth.log": "Sep 30 12:00:10 ubuntu sshd[8412]: Accepted password for root from 10.0.2.15 port 45123 ssh2\r\n",
                                "id_rsa": "-----BEGIN OPENSSH PRIVATE KEY-----\r\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlw==\r\n-----END OPENSSH PRIVATE KEY-----\r\n"
                            }
                            content = mock_contents.get(target, f"# Content of {target}\r\n")
                            channel.send(content.encode("utf-8"))
                        elif target_path in virtual_fs:
                            channel.send(f"cat: {target}: Is a directory\r\n".encode())
                        else:
                            channel.send(f"cat: {target}: No such file or directory\r\n".encode())

                    elif cmd.startswith("cd "):
                        target = cmd.split(" ", 1)[1].strip()
                        if target.startswith("/"):
                            new_dir = os.path.normpath(target)
                        else:
                            new_dir = os.path.normpath(os.path.join(current_dir, target))
                        
                        new_dir = new_dir.replace("\\", "/")
                        
                        if new_dir in virtual_fs:
                            current_dir = new_dir
                        else:
                            channel.send(f"cd: {target}: No such file or directory\r\n".encode())
                                
                    elif cmd == "cd":
                        current_dir = "/root"
                        
                    elif cmd == "":
                        pass
                        
                    else:
                        channel.send(f"bash: {cmd}: command not found\r\n".encode())
                    
                    channel.send(f"root@ubuntu:{current_dir}# ".encode())
                    buffer = b""
                
                else:
                    buffer += char
                    channel.send(char)
                    
    except Exception as e:
        print(f"[-] Erreur dans le faux shell : {e}")
    finally:
        channel.close()