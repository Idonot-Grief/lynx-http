import os
import sys
import socket
import threading
import mimetypes
import json as pyjson
import traceback
import subprocess
from urllib.parse import unquote_plus, parse_qs
import base64
import hashlib
import time
import ssl

# --- PATH CONFIGURATION ---
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WEB_ROOT = os.path.join(BASE_DIR, "root")
CONFIG_FILE = os.path.join(BASE_DIR, "config", "server.json")
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins", "wsp")
CACHE_FILE = os.path.join(BASE_DIR, "cache.dat")
FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg")

mimetypes.init()

# --- CONFIG LOADING ---
default_config = {
    "host": "0.0.0.0",
    "port": 8080,
    "ip_whitelist_enabled": False,
    "ip_whitelist": ["127.0.0.1"],
    "browsable_dirs": ["/"],
    "favicon": "/favicon.ico"
}

def load_config():
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            pyjson.dump(default_config, f, indent=4)
        return default_config
    try:
        with open(CONFIG_FILE, "r") as f:
            conf = default_config.copy()
            conf.update(pyjson.load(f))
            return conf
    except:
        return default_config

config = load_config()

# --- CACHE MANAGEMENT ---
def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return pyjson.load(f)
    except:
        return {}

def save_cache(new_cache_data):
    global cache
    cache.update(new_cache_data)
    with open(CACHE_FILE, "w") as f:
        pyjson.dump(cache, f, indent=2)

cache = load_cache()

# --- PLUGIN SYSTEM ---
plugin_hooks = {
    "before_request": [],
    "after_request": [],
    "websocket_connect": [], # Placeholder for future WS support
    "websocket_message": [],
    "websocket_close": []
}

pre_imports = {
    "os": os, "sys": sys, "socket": socket, "threading": threading,
    "mimetypes": mimetypes, "json": pyjson, "traceback": traceback,
    "unquote_plus": unquote_plus, "parse_qs": parse_qs,
    "subprocess": subprocess, "cache": cache, "save_cache": save_cache,
    "FFMPEG_DIR": FFMPEG_DIR, "time": time, "hashlib": hashlib,
    "base64": base64, "ssl": ssl
}

def load_plugins():
    os.makedirs(PLUGINS_DIR, exist_ok=True)
    for filename in os.listdir(PLUGINS_DIR):
        if filename.endswith(".wsp"):
            try:
                plugin_path = os.path.join(PLUGINS_DIR, filename)
                plugin_name = filename[:-4]
                plugin_folder = os.path.join(BASE_DIR, "plugins", plugin_name)
                os.makedirs(plugin_folder, exist_ok=True)
                
                globals_dict = pre_imports.copy()
                globals_dict.update({
                    "__file__": plugin_path,
                    "__name__": plugin_name,
                    "__plugin_folder__": plugin_folder,
                    "plugin_hooks": plugin_hooks
                })
                
                with open(plugin_path, "r") as f:
                    exec(f.read(), globals_dict)
                print(f"[PLUGIN] Loaded {filename}")
            except Exception as e:
                print(f"[PLUGIN ERROR] {filename}: {e}")

# --- HTTP UTILITIES ---
def http_response(status, headers=None, body=b""):
    reasons = {200: "OK", 404: "Not Found", 400: "Bad Request", 500: "Internal Server Error", 403: "Forbidden"}
    reason = reasons.get(status, "OK")
    
    # Ensure Content-Length is set correctly
    headers = headers or {}
    if body and "Content-Length" not in headers:
        headers["Content-Length"] = str(len(body))
    
    header_lines = [f"HTTP/1.1 {status} {reason}"]
    for k, v in headers.items():
        header_lines.append(f"{k}: {v}")
    
    return "\r\n".join(header_lines).encode() + b"\r\n\r\n" + body

def parse_request(data):
    try:
        header_part = data.split("\r\n\r\n", 1)[0]
        lines = header_part.split("\r\n")
        if not lines[0]: return None
        
        parts = lines[0].split()
        if len(parts) < 3: return None
        method, path, version = parts
        
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        
        body = ""
        if "\r\n\r\n" in data:
            body = data.split("\r\n\r\n", 1)[1]
            
        return {"method": method, "path": path, "version": version, "headers": headers, "body": body}
    except Exception:
        return None

def sanitize_path(request_path):
    # Remove query strings and leading slashes
    clean_path = unquote_plus(request_path.split("?", 1)[0]).lstrip("/")
    # Join with WEB_ROOT and then check if the resulting path is still inside WEB_ROOT
    full_path = os.path.abspath(os.path.join(WEB_ROOT, clean_path))
    if not full_path.startswith(os.path.abspath(WEB_ROOT)):
        return None
    return full_path

# --- CORE HANDLER ---
def handle_client(conn, addr):
    try:
        conn.settimeout(5.0)
        data = conn.recv(8192).decode(errors="ignore")
        if not data: return
        
        request = parse_request(data)
        if not request:
            conn.sendall(http_response(400))
            return
        request["client_socket"] = conn
        request["client_addr"] = addr

        # 1. IP Whitelist Check
        if config.get("ip_whitelist_enabled") and addr[0] not in config.get("ip_whitelist", []):
            conn.sendall(http_response(403, body=b"IP Not Authorized"))
            return

        # 2. Before Request Hook
        for hook in plugin_hooks["before_request"]:
            try: hook(request)
            except: pass

        # 3. Path Resolution
        target_path = sanitize_path(request['path'])
        if not target_path:
            conn.sendall(http_response(404, body=b"Invalid Path"))
            return

        # 4. Routing Logic
        response = {"status": 200, "headers": {}, "body": b""}

        if os.path.isdir(target_path):
            index_file = os.path.join(target_path, "index.html")
            if os.path.isfile(index_file):
                target_path = index_file
            else:
                # Directory Listing
                rel_path = "/" + os.path.relpath(target_path, WEB_ROOT).replace("\\", "/")
                if rel_path in config.get("browsable_dirs", []):
                    files = os.listdir(target_path)
                    listing = f"<html><body><h1>Listing: {rel_path}</h1><ul>"
                    for f in files:
                        listing += f'<li><a href="{os.path.join(rel_path, f)}">{f}</a></li>'
                    listing += "</ul></body></html>"
                    response["body"] = listing.encode()
                    response["headers"]["Content-Type"] = "text/html"
                else:
                    conn.sendall(http_response(403, body=b"Directory Access Forbidden"))
                    return

        if not response["body"]: # If not already handled by directory listing
            if os.path.isfile(target_path):
                with open(target_path, "rb") as f:
                    response["body"] = f.read()
                mime, _ = mimetypes.guess_type(target_path)
                response["headers"]["Content-Type"] = mime or "application/octet-stream"
            else:
                conn.sendall(http_response(404, body=b"File Not Found"))
                return

        # 5. After Request Hook
        for hook in plugin_hooks["after_request"]:
            try: hook(request, response)
            except: pass

        conn.sendall(http_response(response["status"], response["headers"], response["body"]))

    except Exception as e:
        print(f"[ERROR] {addr}: {e}")
        try: conn.sendall(http_response(500, body=b"Internal Server Error"))
        except: pass
    finally:
        conn.close()

# --- SERVER STARTUP ---
def start_server():
    os.makedirs(WEB_ROOT, exist_ok=True)
    load_plugins()

    use_https = cache.get("https_enabled", False)
    cert_file = cache.get("https_cert")
    key_file = cache.get("https_key")

    ssl_context = None
    if use_https and cert_file and key_file:
        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
            print("[*] HTTPS Context Initialized")
        except Exception as e:
            print(f"[HTTPS ERROR] Setup failed: {e}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((config.get("host"), config.get("port")))
        s.listen(50)
        print(f"[*] Lynx 1.6 listening on {config.get('host')}:{config.get('port')}")

        while True:
            conn, addr = s.accept()
            if ssl_context:
                try:
                    conn = ssl_context.wrap_socket(conn, server_side=True)
                except Exception as e:
                    print(f"[SSL HANDSHAKE ERROR] {addr}: {e}")
                    conn.close()
                    continue
            
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()
