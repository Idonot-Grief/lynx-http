# Web Server Plugin Documentation (Updated with HTTPS/Redirect)

This document describes how to write plugins (`.wsp` files) for the Python web server. Plugins extend server behavior and can interact with HTTP requests, WebSockets, cache, and the filesystem.

---

## 1. Plugin Basics

* **File format:** `.wsp`
* **Location:** `./plugins/wsp/`
* **Plugin folder:** `./plugins/<plugin_name>/` (auto-created)
* **Execution:** Plugins have access to **pre-imported libraries** and shared variables.

**Default variables:**

| Variable            | Description                                     |
| ------------------- | ----------------------------------------------- |
| `__file__`          | Full path to plugin file                        |
| `__name__`          | Plugin name (filename without `.wsp`)           |
| `__plugin_folder__` | Plugin folder path (`./plugins/<plugin_name>/`) |
| `plugin_hooks`      | Dictionary of hooks to append functions         |
| `cache`             | Persistent dictionary shared across plugins     |
| `save_cache(cache)` | Save cache to disk                              |
| `FFMPEG_DIR`        | Path to `./ffmpeg/`                             |

**Pre-imported libraries:**

* `os`, `sys`, `socket`, `threading`, `mimetypes`, `json`, `traceback`, `subprocess`
* `unquote_plus`, `parse_qs`, `hashlib`, `base64`, `time`
* `ssl`, `http`, `http_client`, `urllib_request`, `urllib_parse`, `urllib_error`
* `math`, `re`

---

## 2. Plugin Hooks

| Hook                | Description                      | Function Signature       |
| ------------------- | -------------------------------- | ------------------------ |
| `before_request`    | Runs **before** request handling | `func(request)`          |
| `after_request`     | Runs **after** request handling  | `func(request,response)` |
| `websocket_connect` | WebSocket connect                | `func(conn,addr)`        |
| `websocket_message` | WebSocket message                | `func(conn,addr,msg)`    |
| `websocket_close`   | WebSocket disconnect             | `func(conn,addr)`        |

---

## 3. HTTPS Plugins

Plugins can now:

* Enable HTTPS by setting `cache["https_enabled"] = True`
* Provide certificate paths:
  `cache["https_cert"]`, `cache["https_key"]`
* Auto-redirect HTTP → HTTPS by modifying `response` in `after_request`
* Add HSTS headers

**Example: HTTPS redirect**

```python
def redirect_http_to_https(request,response):
    if cache.get("https_enabled") and request['headers'].get("x-forwarded-proto","http")=="http":
        host = request['headers'].get("host","example.com")
        url = f"https://{host}{request['path']}"
        response["status"] = 301
        response["headers"] = {"Location": url}
        response["body"] = b""

plugin_hooks["after_request"].append(redirect_http_to_https)
```

---

## 4. Persistent Cache

Plugins can share state:

```python
cache['visits'] = cache.get('visits',0)+1
save_cache(cache)
```

---

## 5. FFmpeg Integration

Use `FFMPEG_DIR`:

```python
ffmpeg = os.path.join(FFMPEG_DIR, 'ffmpeg.exe')
subprocess.Popen([ffmpeg,'-i','input.mp4','output.mp4'])
```

---

## 6. Security Considerations

* Plugins run with server permissions
* Validate paths and inputs
* HTTPS should only be enabled with valid certs
* Catch exceptions to prevent server crashes

---

## 7. Tips

* Keep plugins modular in `__plugin_folder__`
* Use `cache` for persistent state
* Use hooks to modify requests/responses

---
