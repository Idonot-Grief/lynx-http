# Web Server Plugin Documentation

This document describes how to write plugins (`.wsp` files) for the Python web server. Plugins extend the server’s behavior and can interact with HTTP requests, WebSockets, cache, and the filesystem.

---

## 1. Plugin Basics

- **File format:** `.wsp`
- **Location:** `./plugins/wsp/`
- **Plugin folder:** `./plugins/<plugin_name>/` (automatically created)
- **Execution:** Plugins are executed with access to a set of **pre-imported standard libraries**.

**Default available variables:**

| Variable | Description |
|----------|-------------|
| `__file__` | Full path to the plugin file |
| `__name__` | Plugin name (filename without `.wsp`) |
| `__plugin_folder__` | Folder for plugin-specific files (`./plugins/<plugin_name>/`) |
| `plugin_hooks` | Dictionary of hooks you can append functions to |
| `cache` | Persistent dictionary shared across plugins |
| `save_cache(cache)` | Function to save the cache to disk |
| `FFMPEG_DIR` | Path to `./ffmpeg/` directory |

**Pre-imported standard libraries available:**

- `os`, `socket`, `threading`, `mimetypes`, `json`, `traceback`, `subprocess`  
- `unquote_plus`, `parse_qs`, `hashlib`, `base64`, `time`  
- `ssl`, `http`, `http_client`, `urllib_request`, `urllib_parse`, `urllib_error`  
- `sys`, `math`, `re`  

Plugins do **not need to import these libraries**; they can use them directly.

---

## 2. Plugin Hooks

The `plugin_hooks` dictionary allows plugins to hook into server events. You can append your functions to the following hooks:

| Hook | Description | Function Signature |
|------|-------------|------------------|
| `before_request` | Runs **before** the server processes a request | `func(request)` |
| `after_request` | Runs **after** the server prepares a response, allows modification | `func(request, response)` |
| `websocket_connect` | Runs when a WebSocket connects | `func(conn, addr)` |
| `websocket_message` | Runs when a WebSocket message is received | `func(conn, addr, message)` |
| `websocket_close` | Runs when a WebSocket disconnects | `func(conn, addr)` |

**Request object (`request`):**
```python
{
  'method': 'GET' or 'POST',
  'path': '/requested/path',
  'version': 'HTTP/1.1',
  'headers': { 'header-name': 'value', ... },
  'body': 'raw POST body',
  'client': socket_object
}
```

**Response object (`response`) for `after_request`:**
```python
{
  'status': 200,  # HTTP status code
  'headers': {'Content-Type': 'text/html', ...},
  'body': b'byte content of response'
}
```

---

## 3. Writing a Basic Plugin

Example: `default.wsp` that initializes the root folder:

```python
# default.wsp
# Ensure root exists
if not os.path.exists('./root'):
    os.makedirs('./root', exist_ok=True)

# Ensure plugin folder exists
if not os.path.exists(__plugin_folder__):
    os.makedirs(__plugin_folder__, exist_ok=True)

# Initialize cache for this plugin
if 'default_plugin_initialized' not in cache:
    cache['default_plugin_initialized'] = True
    save_cache(cache)
```

---

## 4. HTTP Request Handling

Plugins can inspect and modify requests or responses:

```python
def log_requests(request):
    print(f"Incoming request: {request['method']} {request['path']}")
plugin_hooks['before_request'].append(log_requests)
```

Modify response:

```python
def custom_header(request, response):
    response['headers']['X-Custom'] = 'Hello'
plugin_hooks['after_request'].append(custom_header)
```

---

## 5. WebSocket Plugins

```python
def on_connect(conn, addr):
    print(f"WebSocket connected: {addr}")

def on_message(conn, addr, msg):
    print(f"Message from {addr}: {msg}")
    conn.sendall(msg)  # echo back

plugin_hooks['websocket_connect'].append(on_connect)
plugin_hooks['websocket_message'].append(on_message)
```

---

## 6. Persistent Cache

- Access shared data across plugins using `cache` dictionary.
- Save changes with `save_cache(cache)`.

```python
# Increment visit count
cache['visits'] = cache.get('visits', 0) + 1
save_cache(cache)
```

---

## 7. FFmpeg Integration

Plugins can use `FFMPEG_DIR` to run ffmpeg tools:

```python
ffmpeg = os.path.join(FFMPEG_DIR, 'ffmpeg.exe')
subprocess.Popen([ffmpeg, '-i', 'input.mp4', 'output.mp4'])
```

---

## 8. Security Considerations

- Plugins run with full server permissions.  
- Validate paths and inputs to avoid directory traversal.  
- Use HTTPS libraries if needed (`ssl`, `urllib_request`) for secure requests.  

---

## 9. Tips

- Keep plugins modular: use `__plugin_folder__` for plugin-specific files.  
- Use `cache` for persistent state.  
- Always catch exceptions to prevent plugin crashes from stopping the server.  

---

**End of Documentation**

