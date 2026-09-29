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
                        files = virtual_fs.get(current_dir, [])
                        channel.send("  ".join(files).encode() + b"\r\n")
                        
                    elif cmd.startswith("cd "):
                        target = cmd.split(" ", 1)[1].strip()
                        if target == "..":
                            if current_dir != "/":
                                current_dir = os.path.dirname(current_dir)
                                if current_dir == "": current_dir = "/"
                        elif target.startswith("/"):
                            if target in virtual_fs:
                                current_dir = target
                            else:
                                channel.send(f"cd: {target}: No such file or directory\r\n".encode())
                        else:
                            new_dir = os.path.join(current_dir, target).replace("\\", "/")
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