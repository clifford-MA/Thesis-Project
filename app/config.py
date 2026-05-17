import socket
import platform
import threading
import time
import sys
import os

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

IS_SERVER = True

SERVER_IP_OVERRIDE = None

SERVER_PORT      = 5000
DISCOVERY_PORT   = 5001
DISCOVERY_MSG    = b"QUEUE_SERVER_DISCOVERY"
DISCOVERY_REPLY  = b"QUEUE_SERVER_HERE:"

def get_own_ip():
    """
    Get this computer's IP on the current network.
    Tries hotspot/LAN ranges first (10.x, 192.168.x, 172.x),
    then falls back to internet routing.
    """
    test_targets = [
        ("10.255.255.255", 1),
        ("192.168.255.255", 1),
        ("172.16.255.255", 1),
        ("8.8.8.8", 80),
    ]
    for host, port in test_targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect((host, port))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            continue

    try:
        results = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        for result in results:
            ip = result[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"

def start_discovery_broadcaster(server_ip):
    """
    Runs in background thread.
    Continuously broadcasts server IP on the local network.
    Clients listen for this to auto-connect.
    """
    def broadcast_loop():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        message = DISCOVERY_REPLY + server_ip.encode()
        print(f"[DISCOVERY] Broadcasting server IP: {server_ip} on port {DISCOVERY_PORT}")
        while True:
            try:
                sock.sendto(message, ("<broadcast>", DISCOVERY_PORT))
            except Exception as e:
                print(f"[DISCOVERY] Broadcast error: {e}")
            time.sleep(1)

    t = threading.Thread(target=broadcast_loop, daemon=True)
    t.start()

def discover_server_ip(timeout=5):
    """
    Listen for the server's UDP broadcast and return its IP.
    Waits up to `timeout` seconds before giving up.
    """
    print(f"[DISCOVERY] Listening for server on port {DISCOVERY_PORT} (timeout: {timeout}s)...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.bind(("", DISCOVERY_PORT))

        while True:
            try:
                data, addr = sock.recvfrom(1024)
                if data.startswith(DISCOVERY_REPLY):
                    server_ip = data[len(DISCOVERY_REPLY):].decode().strip()
                    print(f"[DISCOVERY] ✓ Server found at: {server_ip} (broadcast from {addr[0]})")
                    sock.close()
                    return server_ip
            except socket.timeout:
                print("[DISCOVERY] ⚠️  No server found within timeout.")
                break
            except Exception as e:
                print(f"[DISCOVERY] Error: {e}")
                break

        sock.close()
    except Exception as e:
        print(f"[DISCOVERY] Could not open discovery socket: {e}")

    return None

if IS_SERVER:
    SERVER_IP = get_own_ip()
    print(f"[CONFIG] SERVER mode — detected IP: {SERVER_IP}")
    start_discovery_broadcaster(SERVER_IP)

else:
    if SERVER_IP_OVERRIDE:
        SERVER_IP = SERVER_IP_OVERRIDE
        print(f"[CONFIG] CLIENT mode — using manual override IP: {SERVER_IP}")
    else:
        SERVER_IP = discover_server_ip(timeout=5)

        if not SERVER_IP:
            print("[CONFIG] ════════════════════════════════════════════════════════")
            print("[CONFIG] ❌ Could not find server automatically!")
            print("[CONFIG]")
            print("[CONFIG] Make sure the SERVER computer is running first.")
            print("[CONFIG] If it still fails, open config.py and set:")
            print("[CONFIG]   SERVER_IP_OVERRIDE = \"<server IP here>\"")
            print("[CONFIG] ════════════════════════════════════════════════════════")
            SERVER_IP = "127.0.0.1"

def get_system_info():
    try:
        return {
            "hostname": socket.gethostname(),
            "platform": platform.system(),
        }
    except Exception:
        return {}

print("\n" + "=" * 80)
print("  QUEUE MANAGEMENT SYSTEM - CONFIGURATION")
print("=" * 80)
print(f"  Mode:        {'SERVER' if IS_SERVER else 'CLIENT'}")
print(f"  Server IP:   {SERVER_IP}   <-- both server and clients should show same IP")
print(f"  Server Port: {SERVER_PORT}")
_info = get_system_info()
if _info:
    print(f"  Hostname:    {_info.get('hostname', 'Unknown')}")
    print(f"  Platform:    {_info.get('platform', 'Unknown')}")
    print(f"  This PC IP:  {get_own_ip()}")
print("=" * 80 + "\n")

if IS_SERVER:
    API_BASE_URL = f"http://localhost:{SERVER_PORT}/api"
    SERVER_URL   = f"http://localhost:{SERVER_PORT}"
else:
    API_BASE_URL = f"http://{SERVER_IP}:{SERVER_PORT}/api"
    SERVER_URL   = f"http://{SERVER_IP}:{SERVER_PORT}"

print(f"[CONFIG] API_BASE_URL: {API_BASE_URL}")
print(f"[CONFIG] SERVER_URL:   {SERVER_URL}")
print()

REQUEST_TIMEOUT       = 3
FAST_TIMEOUT          = 2
AUTO_REFRESH_INTERVAL = 3000

__all__ = [
    'IS_SERVER',
    'SERVER_IP',
    'SERVER_PORT',
    'API_BASE_URL',
    'SERVER_URL',
    'REQUEST_TIMEOUT',
    'FAST_TIMEOUT',
    'AUTO_REFRESH_INTERVAL',
]

