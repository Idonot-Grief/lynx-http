# Lynx Web Server 1.5
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

# --- HANDLE PATHS WHEN FROZEN ---
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WEB_ROOT = os.path.join(BASE_DIR, "root")
CONFIG_FILE = os.path.join(BASE_DIR, "config", "server.json")
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins", "wsp")
CACHE_FILE = os.path.join(BASE_DIR, "cache.dat")
FFMPEG_DIR = os.path.join(BASE_DIR, "ffmpeg")

HOST = "0.0.0.0"
PORT = 8080

mimetypes.init()

# --- CONFIG ---
default_config = {
    "host": HOST,
    "port": PORT,
    "ip_whitelist_enabled": False,
    "ip_whitelist": ["127.0.0.1"],
    "browsable_dirs": ["/"],
    "favicon": "/favicon.ico"
}

os.makedirs(os.path.join(BASE_DIR, "config"), exist_ok=True)
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        f.write(pyjson.dumps(default_config, indent=4))

config = default_config
try:
    with open(CONFIG_FILE, "r") as f:
        config.update(pyjson.loads(f.read()))
except:
    config = default_config

# --- CACHE ---
if not os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "w") as f:
        f.write("{}")

def load_cache():
    with open(CACHE_FILE, "r") as f:
        try: return pyjson.loads(f.read())
        except: return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        f.write(pyjson.dumps(cache, indent=2))

cache = load_cache()

# --- PLUGIN HOOKS ---
plugin_hooks = {
    "before_request": [],
    "after_request": [],
    "websocket_connect": [],
    "websocket_message": [],
    "websocket_close": []
}

# --- PRE-IMPORTS FOR PLUGINS ---
pre_imports = {
    "os": os,
    "sys": sys,
    "socket": socket,
    "threading": threading,
    "mimetypes": mimetypes,
    "json": pyjson,
    "traceback": traceback,
    "unquote_plus": unquote_plus,
    "parse_qs": parse_qs,
    "subprocess": subprocess,
    "cache": cache,
    "save_cache": save_cache,
    "FFMPEG_DIR": FFMPEG_DIR,
    "time": time,
    "hashlib": hashlib,
    "base64": base64,
    "ssl": __import__("ssl"),
    "http": __import__("http"),
    "http_client": __import__("http.client"),
    "urllib_request": __import__("urllib.request"),
    "urllib_parse": __import__("urllib.parse"),
    "urllib_error": __import__("urllib.error"),
    "math": __import__("math"),
    "re": __import__("re"),
}

# --- LOAD PLUGINS ---
os.makedirs(PLUGINS_DIR, exist_ok=True)
loaded_plugins = []

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
            with open(plugin_path,"r") as f:
                exec(f.read(), globals_dict)
            loaded_plugins.append(plugin_name)
            print(f"[PLUGIN] Loaded {filename}")
        except Exception as e:
            print(f"[PLUGIN ERROR] {filename}: {e}")

# --- HTTP HELPERS ---
def http_response(status, headers=None, body=b""):
    reasons = {200:"OK",404:"Not Found",400:"Bad Request",500:"Internal Server Error",403:"Forbidden"}
    reason = reasons.get(status,"OK")
    header_lines = [f"HTTP/1.1 {status} {reason}"]
    if headers:
        for k,v in headers.items():
            header_lines.append(f"{k}: {v}")
    header_lines.append("")
    header_lines.append("")
    return "\r\n".join(header_lines).encode() + body

def parse_request(data):
    try:
        lines = data.split("\r\n")
        method,path,version = lines[0].split()
        headers = {}
        body = ""
        for line in lines[1:]:
            if line=="": break
            parts = line.split(":",1)
            if len(parts)==2: headers[parts[0].strip().lower()] = parts[1].strip()
        if method=="POST" and "\r\n\r\n" in data:
            body = data.split("\r\n\r\n",1)[1]
        return {"method": method, "path": path, "version": version, "headers": headers, "body": body, "client": None}
    except:
        return None

def sanitize_path(path):
    path = unquote_plus(path.split("?",1)[0])
    path = os.path.normpath(path.lstrip("/"))
    if ".." in path: return None
    return os.path.join(WEB_ROOT, path)

def handle_directory(path, request_path):
    listing="<html><body><h1>Directory listing</h1><ul>"
    try:
        for file in os.listdir(path):
            fpath = os.path.join(request_path, file)
            listing += f'<li><a href="{fpath}">{file}</a></li>'
        listing+="</ul></body></html>"
        return listing.encode()
    except:
        return b"Error listing directory"

# --- CLIENT HANDLER ---
def handle_client(conn, addr):
    try:
        data = conn.recv(8192).decode(errors="ignore")
        if not data: return
        request = parse_request(data)
        if not request:
            conn.sendall(http_response(400,{"Content-Length":"0"}))
            return
        request["client"] = conn

        # IP whitelist
        if config.get("ip_whitelist_enabled") and addr[0] not in config.get("ip_whitelist",[]):
            body=b"403 Forbidden"
            conn.sendall(http_response(403,{"Content-Length":str(len(body))},body))
            return

        # BEFORE REQUEST PLUGINS
        for hook in plugin_hooks["before_request"]:
            try: hook(request)
            except: pass

        path = sanitize_path(request['path'])
        if not path:
            body=b"404 Not Found"
            conn.sendall(http_response(404,{"Content-Length":str(len(body))},body))
            return

        # favicon
        if request['path']=="/favicon.ico" and config.get("favicon"):
            favicon_path = sanitize_path(config.get("favicon"))
            if favicon_path and os.path.isfile(favicon_path):
                with open(favicon_path,"rb") as f: body=f.read()
                conn.sendall(http_response(200,{"Content-Type":"image/x-icon","Content-Length":str(len(body))},body))
                return

        # directory
        if os.path.isdir(path):
            index_file = os.path.join(path,"index.html")
            if os.path.isfile(index_file):
                path = index_file
            else:
                rel_path="/"+os.path.relpath(path,WEB_ROOT).replace("\\","/")
                if rel_path not in config.get("browsable_dirs",[]): 
                    body=b"403 Forbidden"
                    conn.sendall(http_response(403,{"Content-Length":str(len(body))},body))
                    return
                body=handle_directory(path,rel_path)
                conn.sendall(http_response(200,{"Content-Type":"text/html","Content-Length":str(len(body))},body))
                return

        if not os.path.isfile(path):
            body=b"404 Not Found"
            conn.sendall(http_response(404,{"Content-Length":str(len(body))},body))
            return

        # GET/POST
        if request['method']=="GET":
            with open(path,"rb") as f: body=f.read()
            mime,_=mimetypes.guess_type(path)
            if not mime: mime="application/octet-stream"
            response={"status":200,"headers":{"Content-Type":mime,"Content-Length":str(len(body))},"body":body}
        elif request['method']=="POST":
            response={"status":200,"headers":{"Content-Type":"text/html"},"body":f"<html><body><pre>{parse_qs(request['body'])}</pre></body></html>".encode()}
        else:
            response={"status":400,"headers":{"Content-Length":"0"},"body":b""}

        # AFTER REQUEST PLUGINS
        for hook in plugin_hooks["after_request"]:
            try: hook(request,response)
            except: pass

        conn.sendall(http_response(response["status"],response["headers"],response["body"]))

    except Exception as e:
        print(f"[ERROR] {addr}: {e}\n{traceback.format_exc()}")
        body=b"500 Internal Server Error"
        conn.sendall(http_response(500,{"Content-Length":str(len(body))},body))
    finally:
        conn.close()

# --- SERVER START ---
def start_server():
    os.makedirs(WEB_ROOT, exist_ok=True)
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        s.bind((config.get("host",HOST), config.get("port",PORT)))
        s.listen(50)
        print(f"[*] Serving {os.path.abspath(WEB_ROOT)} on {config.get('host')}:{config.get('port')}")
        while True:
            conn,addr = s.accept()
            threading.Thread(target=handle_client, args=(conn,addr), daemon=True).start()

if __name__=="__main__":
    start_server()
