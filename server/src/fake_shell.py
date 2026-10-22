# src/fake_shell.py
import os
from database import log_command

MAX_COMMAND_LENGTH = 4096


def handle_fake_shell(channel, client_ip, port=2222):
    try:
        channel.settimeout(300)
        virtual_fs = {
            "/root": [".bashrc", ".bash_history", ".ssh", "scripts", "backup.tar.gz"],
            "/root/.ssh": ["authorized_keys", "id_rsa", "id_rsa.pub", "known_hosts"],
            "/root/scripts": ["cleanup.sh", "health_check.py", "deploy.sh"],
            "/etc": ["passwd", "shadow", "hosts", "resolv.conf", "crontab", "nginx", "ssh", "systemd"],
            "/etc/nginx": ["nginx.conf", "sites-available", "sites-enabled"],
            "/etc/nginx/sites-available": ["default", "api.conf", "internal-portal.conf"],
            "/etc/nginx/sites-enabled": ["default", "api.conf"],
            "/etc/ssh": ["sshd_config", "ssh_config"],
            "/home": ["ubuntu", "deploy", "sysadmin"],
            "/home/ubuntu": [".bashrc", ".profile", ".ssh", "webapp", "notes.txt"],
            "/home/ubuntu/.ssh": ["authorized_keys"],
            "/home/ubuntu/webapp": ["package.json", "server.js", ".env", "README.md"],
            "/var/log": ["auth.log", "syslog", "kern.log", "nginx", "apt", "dpkg.log"],
            "/var/log/nginx": ["access.log", "error.log"],
            "/var/log/apt": ["history.log", "term.log"],
            "/var/www/html": ["index.html", "admin.php", "config.php", "robots.txt", "uploads"],
            "/var/www/html/uploads": [".htaccess", "logo.png"],
            "/tmp": [".X11-unix", "systemd-private-nginx.service"]
        }
        
        file_contents = {
            "passwd": "root:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\nubuntu:x:1000:1000:Ubuntu,,,:/home/ubuntu:/bin/bash\ndeploy:x:1001:1001,,,:/home/deploy:/bin/bash\n\r\n",
            "hosts": "127.0.0.1 localhost\n127.0.1.1 ubuntu-srv-prod-01\n\n# ::1 localhost ip6-localhost ip6-loopback\n\r\n",
            "resolv.conf": "nameserver 1.1.1.1\nnameserver 8.8.8.8\n\r\n",
            "crontab": "SHELL=/bin/sh\nPATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n\n17 * * * * root cd / && run-parts --report /etc/cron.hourly\n25 6 * * * root test -x /usr/sbin/anacron || ( cd / && run-parts --report /etc/cron.daily )\n\r\n",
            "notes.txt": "Rappels migration:\n- Mettre a jour le certificat SSL du portail interne avant le 15.\n- Verifier les acces base de donnees sur le cluster principal.\n\r\n",
            ".env": "DB_HOST=127.0.0.1\nDB_PORT=5432\nDB_NAME=production_db\nJWT_SECRET=9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c\n\r\n",
            "auth.log": "Sep 30 12:00:10 ubuntu sshd[8412]: Accepted password for root from 10.0.2.15 port 45123 ssh2\r\nSep 30 12:05:22 ubuntu sshd[8520]: Failed password for invalid user admin from 192.168.1.50 port 51200 ssh2\r\n",
            "access.log": "192.168.1.10 - - [22/Oct/2026:09:12:04 +0200] \"GET / HTTP/1.1\" 200 612 \"-\" \"Mozilla/5.0\"\n10.0.4.2 - - [22/Oct/2026:09:15:30 +0200] \"POST /admin.php HTTP/1.1\" 403 154 \"-\" \"Nikto/2.1.6\"\r\n",
            "id_rsa": "-----BEGIN OPENSSH PRIVATE KEY-----\r\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlw==\r\n-----END OPENSSH PRIVATE KEY-----\r\n",
            "config.json": '{\n    "db_host": "127.0.0.1",\n    "db_user": "admin",\n    "secret_token": "a8f5c3e921b"\n}\r\n'
        }
        
        current_dir = "/root"

        channel.send(b"Welcome to Ubuntu 22.04.3 LTS (GNU/Linux 5.15.0-88-generic x86_64)\r\n\r\n")
        channel.send(f"root@ubuntu:{current_dir}# ".encode())
        
        buffer = b""
        overflow_bytes = 0
        while True:
            data = channel.recv(1024)
            if not data:
                break
            
            for byte in data:
                char = bytes([byte])
                
                if char in (b'\x7f', b'\b'):
                    if overflow_bytes:
                        overflow_bytes -= 1
                        channel.send(b'\b \b')
                    elif len(buffer) > 0:
                        buffer = buffer[:-1]
                        channel.send(b'\b \b')
                
                elif char == b'\t' and overflow_bytes:
                    channel.send(b'\x07')

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

                elif char in (b'\n', b'\r'):
                    channel.send(b"\r\n")
                    cmd = buffer.decode("utf-8", errors="ignore").strip()
                    print(f"[CMD] IP: {client_ip} | Commande interceptée à {current_dir} : {cmd}")
                    
                    response_buffer = []
                    def shell_output(data):
                        if isinstance(data, str):
                            b_data = data.encode("utf-8", errors="ignore")
                        else:
                            b_data = data
                        channel.send(b_data)
                        response_buffer.append(b_data.decode("utf-8", errors="ignore"))

                    if overflow_bytes:
                        shell_output(
                            f"bash: command exceeds the {MAX_COMMAND_LENGTH}-byte limit\r\n"
                        )
                    elif cmd.lower() in ("exit", "quit"):
                        shell_output("logout\r\n")
                        if cmd != "":
                            log_command(client_ip, cmd, current_dir, "".join(response_buffer), port=port)
                        return
                        
                    elif cmd.startswith("uname"):
                        shell_output("Linux ubuntu 5.15.0-88-generic #98-Ubuntu SMP Mon Oct 2 15:18:56 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux\r\n")
                        
                    elif cmd.startswith("id"):
                        shell_output("uid=0(root) gid=0(root) groups=0(root)\r\n")
                        
                    elif cmd.startswith("whoami"):
                        shell_output("root\r\n")
                        
                    elif cmd.startswith("pwd"):
                        shell_output(f"{current_dir}\r\n")
                        
                    elif cmd.startswith("ls"):
                        parts = cmd.split()
                        flags = ""
                        for p in parts[1:]:
                            if p.startswith("-"):
                                flags += p[1:]
                        
                        long_format = 'l' in flags
                        show_all = 'a' in flags
                        
                        files = virtual_fs.get(current_dir, [])
                        
                        if not show_all:
                            filtered_files = [f for f in files if not f.startswith('.')]
                        else:
                            filtered_files = ['.', '..'] + [f for f in files if f != '.' and f != '..']
                        
                        if long_format:
                            shell_output("total 28\r\n")
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
                                    size = "2048" if f == "backup.tar.gz" else "220"
                                    
                                line = f"{perms} {links} root root {size:>4} Sep 30 12:00 {f}\r\n"
                                shell_output(line)
                        else:
                            shell_output("  ".join(filtered_files) + "\r\n")
                        
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
                            shell_output(f"mkdir: cannot create directory '{target}': File exists\r\n")

                    elif cmd.startswith("touch "):
                        target = cmd.split(" ", 1)[1].strip()
                        current_files = virtual_fs.setdefault(current_dir, [])
                        if target not in current_files:
                            current_files.append(target)
                        file_contents[target] = ""

                    elif cmd.startswith("echo "):
                        if ">>" in cmd:
                            parts = cmd.split(">>")
                            content_part = parts[0].replace("echo", "").strip().strip('"').strip("'")
                            target_file = parts[1].strip()
                            
                            current_files = virtual_fs.setdefault(current_dir, [])
                            if target_file not in current_files:
                                current_files.append(target_file)
                            
                            existing_content = file_contents.get(target_file, "")
                            file_contents[target_file] = existing_content + content_part + "\r\n"
                            
                        elif ">" in cmd:
                            parts = cmd.split(">")
                            content_part = parts[0].replace("echo", "").strip().strip('"').strip("'")
                            target_file = parts[1].strip()
                            
                            current_files = virtual_fs.setdefault(current_dir, [])
                            if target_file not in current_files:
                                current_files.append(target_file)
                            
                            file_contents[target_file] = content_part + "\r\n"
                        else:
                            text_to_echo = cmd[5:].strip().strip('"').strip("'")
                            shell_output(f"{text_to_echo}\r\n")

                    elif cmd.startswith("cat "):
                        parts = cmd.split("|")
                        cat_part = parts[0].strip()
                        grep_pattern = parts[1].strip().replace("grep ", "").strip('"').strip("'") if len(parts) > 1 else None

                        target = cat_part.split(" ", 1)[1].strip()
                        files_in_dir = virtual_fs.get(current_dir, [])
                        target_path = os.path.normpath(os.path.join(current_dir, target)).replace("\\", "/")
                        
                        if target in files_in_dir and target_path not in virtual_fs:
                            content = file_contents.get(target, "")
                            
                            if grep_pattern:
                                lines = content.splitlines()
                                filtered_lines = [l for l in lines if grep_pattern.lower() in l.lower()]
                                content = "\r\n".join(filtered_lines) + ("\r\n" if filtered_lines else "")

                            shell_output(content)
                        elif target_path in virtual_fs:
                            shell_output(f"cat: {target}: Is a directory\r\n")
                        else:
                            shell_output(f"cat: {target}: No such file or directory\r\n")

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
                            shell_output(f"cd: {target}: No such file or directory\r\n")
                            
                    elif cmd == "cd":
                        current_dir = "/root"
                        
                    elif cmd == "":
                        pass
                        
                    else:
                        shell_output(f"bash: {cmd}: command not found\r\n")
                    
                    if cmd != "":
                        log_command(client_ip, cmd, current_dir, "".join(response_buffer), port=port)
                    
                    shell_output(f"root@ubuntu:{current_dir}# ")
                    buffer = b""
                    overflow_bytes = 0
                
                else:
                    if len(buffer) < MAX_COMMAND_LENGTH:
                        buffer += char
                        channel.send(char)
                    else:
                        overflow_bytes += 1
                        channel.send(b'\x07')
                
    except Exception as e:
        print(f"[-] Erreur dans le faux shell : {e}")
    finally:
        channel.close()