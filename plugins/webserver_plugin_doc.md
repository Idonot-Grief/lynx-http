# Web Server Plugin Documentation

This document describes how to write plugins (`.wsp` files) for the Python web server. Plugins extend server behavior and can interact with HTTP requests, WebSockets, caching, security features, and the filesystem.

---

## 1. Plugin Basics

### File & Execution Model

* **File format:** `.wsp`
* **Location:** `./plugins/wsp/`
* **Plugin data folder:** `./plugins/<plugin_name>/` (automatically created)
* **Execution model:** Plugins are executed by the server at load time. They **do not import libraries themselves** — all supported libraries are pre-imported by the main server and injected into the plugin runtime.

This design ensures:

* Fast startup
* Consistent environments across plugins
* No dependency conflicts

### Default Available Variables

| Variable            | Description                                     |
| ------------------- | ----------------------------------------------- |
| `__file__`          | Absolute path to the plugin file                |
| `__name__`          | Plugin name (filename without `.wsp`)           |
| `__plugin_folder__` | Plugin-specific storage folder                  |
| `plugin_hooks`      | Dictionary of hook lists to append functions to |
| `cache`             | Persistent, shared key-value store              |
| `save_cache(cache)` | Writes cache to disk                            |
| `FFMPEG_DIR`        | Path to bundled ffmpeg binaries                 |

### Pre-imported Libraries

Plugins may use these directly **without importing**:

* `os`, `sys`, `socket`, `threading`, `mimetypes`, `json`, `traceback`, `subprocess`
* `time`, `math`, `re`, `hashlib`, `base64`
* `unquote_plus`, `parse_qs`
* `ssl`, `http`, `http_client`
* `urllib_request`, `urllib_parse`, `urllib_error`

---

## 2. Plugin Lifecycle

Plugins are executed in this order:

1. Server loads `.wsp` file
2. Plugin initializes (top-level code runs)
3. Plugin registers hooks
4. Plugin responds to server events

Plugins should:

* Create their plugin folder if needed
* Initialize cache keys safely
* Never block the main thread

Example initialization:

```python
if not os.path.exists(__plugin_folder__):
    os.makedirs(__plugin_folder__, exist_ok=True)

if 'my_plugin_init' not in cache:
    cache['my_plugin_init'] = True
    save_cache(cache)
```

---

## 3. Hook System

Plugins extend the server by registering functions into hook lists.

### Available Hooks

| Hook                | Purpose                    | Signature                   |
| ------------------- | -------------------------- | --------------------------- |
| `before_request`    | Inspect or modify requests | `func(request)`             |
| `after_request`     | Modify outgoing responses  | `func(request, response)`   |
| `websocket_connect` | WebSocket open             | `func(conn, addr)`          |
| `websocket_message` | WebSocket message          | `func(conn, addr, message)` |
| `websocket_close`   | WebSocket close            | `func(conn, addr)`          |

Hooks run **in registration order**.

---

## 4. HTTP Request & Response Objects

### Request Object

```python
{
  'method': 'GET' | 'POST',
  'path': '/path',
  'version': 'HTTP/1.1',
  'headers': { 'header': 'value' },
  'body': 'raw body',
  'client': socket_object
}
```

### Response Object

```python
{
  'status': 200,
  'headers': {'Content-Type': 'text/html'},
  'body': b'bytes'
}
```

Plugins may modify:

* Status code
* Headers
* Body content

Example:

```python
def add_header(request, response):
    response['headers']['X-Plugin'] = __name__

plugin_hooks['after_request'].append(add_header)
```

---

## 5. Security & Encryption Usage

Plugins can participate in security-related behavior, including:

* Inspecting request headers for secure transport indicators
* Enforcing secure cookies or headers
* Adding headers like:

  * `Strict-Transport-Security`
  * `X-Content-Type-Options`
  * `X-Frame-Options`
  * `Content-Security-Policy`

Example:

```python
def security_headers(request, response):
    response['headers']['X-Content-Type-Options'] = 'nosniff'
    response['headers']['X-Frame-Options'] = 'DENY'

plugin_hooks['after_request'].append(security_headers)
```

Plugins may also use:

* `ssl` for certificate inspection or validation
* `hashlib` for signing or verification
* `base64` for token encoding

> ⚠ Plugins must never generate or handle private keys insecurely.

---

## 6. WebSocket Plugins

WebSocket hooks allow real-time features.

Example echo plugin:

```python
def on_connect(conn, addr):
    print('WS connected', addr)

def on_message(conn, addr, msg):
    conn.sendall(msg)

plugin_hooks['websocket_connect'].append(on_connect)
plugin_hooks['websocket_message'].append(on_message)
```

---

## 7. Persistent Cache

The shared `cache` object persists across restarts.

Best practices:

* Use namespaced keys (`plugin_name:key`)
* Save only JSON-serializable data

Example:

```python
key = f'{__name__}:visits'
cache[key] = cache.get(key, 0) + 1
save_cache(cache)
```

---

## 8. FFmpeg Integration

Plugins can safely call bundled ffmpeg tools.

```python
ffmpeg = os.path.join(FFMPEG_DIR, 'ffmpeg.exe')
subprocess.Popen([ffmpeg, '-i', 'in.mp4', 'out.mp4'])
```

Do not assume system ffmpeg availability.

---

## 9. Error Handling

Plugins must **never crash the server**.

Always wrap risky logic:

```python
def safe_hook(request):
    try:
        pass
    except Exception:
        traceback.print_exc()

plugin_hooks['before_request'].append(safe_hook)
```

---

## 10. Best Practices

* Keep plugins small and focused
* Never block hooks (use threads if needed)
* Validate all paths and input
* Use `__plugin_folder__` for all plugin files
* Document your plugin behavior clearly

---

**End of Documentation**
