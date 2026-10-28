import concurrent.futures
import ipaddress
import time

import paramiko


TARGET_HOST = "127.0.0.1"
TARGET_PORTS = list(dict.fromkeys([
    2222, 2223, 3000, 3001, 3002, 3003, 3004,
    3004, 3005, 3006, 3007, 3008, 3009, 3010
]))
ATTEMPTS_PER_PORT = 50
CONCURRENT_WORKERS = 20
CONNECTION_TIMEOUT = 3
SHELL_TIMEOUT = 5

FAKE_COMMANDS = (
    "whoami",
    "pwd",
    "ls -la",
    "uname -a",
    "cat /etc/passwd",
    "cd /tmp",
    "echo honeypot-test",
)


def read_until_prompt(channel, timeout=SHELL_TIMEOUT):
    output = bytearray()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if channel.recv_ready():
            output.extend(channel.recv(4096))
            if b"# " in output:
                return bytes(output)
        else:
            time.sleep(0.05)

    raise TimeoutError("Le faux shell n’a pas renvoyé son invite à temps.")


def simulate_connection(port):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=TARGET_HOST,
            port=port,
            username="root",
            password="honeypot-test-only",
            timeout=CONNECTION_TIMEOUT,
            banner_timeout=CONNECTION_TIMEOUT,
            auth_timeout=CONNECTION_TIMEOUT,
            allow_agent=False,
            look_for_keys=False,
        )

        channel = client.invoke_shell()
        channel.settimeout(SHELL_TIMEOUT)
        read_until_prompt(channel)

        for command in FAKE_COMMANDS:
            channel.send(command + "\n")
            read_until_prompt(channel)

        return port, True, None
    except (OSError, EOFError, TimeoutError, paramiko.SSHException) as error:
        return port, False, str(error)
    finally:
        client.close()


def main():
    target_ip = ipaddress.ip_address(TARGET_HOST)
    if not target_ip.is_loopback:
        raise ValueError("Ce test est limité à une cible locale (loopback).")

    tasks = [
        port
        for port in TARGET_PORTS
        for _ in range(ATTEMPTS_PER_PORT)
    ]
    print(
        f"[*] Simulation locale sur {TARGET_HOST} : "
        f"{len(TARGET_PORTS)} ports uniques, {len(tasks)} connexions, "
        f"{CONCURRENT_WORKERS} simultanées maximum."
    )

    started_at = time.monotonic()
    results = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=CONCURRENT_WORKERS
    ) as executor:
        futures = [executor.submit(simulate_connection, port) for port in tasks]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    successes_by_port = {port: 0 for port in TARGET_PORTS}
    failures_by_port = {port: 0 for port in TARGET_PORTS}
    first_error_by_port = {}
    for port, succeeded, error in results:
        if succeeded:
            successes_by_port[port] += 1
        else:
            failures_by_port[port] += 1
            first_error_by_port.setdefault(port, error)

    successes = sum(successes_by_port.values())
    print(
        f"[+] Terminé en {time.monotonic() - started_at:.2f}s : "
        f"{successes}/{len(tasks)} sessions SSH et shell complètes."
    )
    for port in TARGET_PORTS:
        failures = failures_by_port[port]
        print(
            f"    Port {port}: {successes_by_port[port]} réussies, "
            f"{failures} échouées"
        )
        if failures:
            print(f"      Première erreur : {first_error_by_port[port] or 'sans détail'}")
    print("[*] Consulte le dashboard pour les attaques et commandes simulées.")


if __name__ == "__main__":
    main()
