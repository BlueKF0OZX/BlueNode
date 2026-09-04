
#!/usr/bin/env python3



import json

import subprocess

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote

from pathlib import Path

from event_logger import emit
from config import load_config
import automation
from remote_admin import ADMIN, MAX_BODY_BYTES, _safe_config



CONFIG = load_config()
WEB_CONFIG = CONFIG.get("web", {})
HOST = str(WEB_CONFIG.get("host", "0.0.0.0"))
PORT = int(WEB_CONFIG.get("port", 8080))

ROOT = Path("/opt/nodesmart")




ACTIONS = {

    "dodropin-connect": "/usr/local/bin/dodropin",

    "dodropin-disconnect": "/usr/local/bin/dodropoff",

    "skywarn-enable": "/usr/local/bin/skywarnon",

    "skywarn-disable": "/usr/local/bin/skywarnoff",

}





class NodeSmartHandler(SimpleHTTPRequestHandler):



    def __init__(self, *args, **kwargs):

        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        path = self.path.split('?', 1)[0]

        if path == '/' or path.startswith('/web/'):
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')

        super().end_headers()



    ALLOWED_STATIC_PATHS = {

        "/web/",

        "/state/recovery.json",

        "/state/intelligence.json",

        "/state/system.json",
        "/state/automation.json",
        "/state/radio_activity.json",
        "/state/connectivity.json",
        "/events/allstar_state.json",
        "/logs/events.log",

    }



    def do_GET(self):

        path = self.path.split("?", 1)[0]

        if path == "/api/admin/session":
            self.send_json(200, ADMIN.public_state(self.admin_cookie()))
            return

        if path == "/api/admin/status":
            if not self.require_admin():
                return
            self.send_json(200, ADMIN.status())
            return

        if path == "/api/admin/logs":
            if not self.require_admin():
                return
            from urllib.parse import parse_qs, urlsplit
            query = parse_qs(urlsplit(self.path).query)
            status, result = ADMIN.logs(query.get("source", [""])[0],
                                        query.get("lines", ["50"])[0])
            self.send_json(status, result)
            return



        # Prevent /web/../ paths from escaping the public web directory.

        if path.startswith("/web/"):

            web_root = (ROOT / "web").resolve()

            decoded_path = unquote(path)
            requested = (ROOT / decoded_path.lstrip("/")).resolve()



            if requested != web_root and web_root not in requested.parents:

                self.send_error(404, "Not Found")

                return



        if path == "/":

            self.send_response(302)

            self.send_header("Location", "/web/")

            self.end_headers()

            return



        if path.startswith("/web/"):

            return super().do_GET()



        if path in self.ALLOWED_STATIC_PATHS:

            return super().do_GET()



        self.send_error(404, "Not Found")



    def do_HEAD(self):

        path = self.path.split('?', 1)[0]



        # Prevent /web/../ paths from escaping the public web directory.

        if path.startswith('/web/'):

            web_root = (ROOT / 'web').resolve()

            decoded_path = unquote(path)
            requested = (ROOT / decoded_path.lstrip('/')).resolve()



            if requested != web_root and web_root not in requested.parents:

                self.send_error(404, 'Not Found')

                return

        if path.startswith('/web/') or path in self.ALLOWED_STATIC_PATHS:
            return super().do_HEAD()

        self.send_error(404, 'Not Found')

    def send_json(self, status_code, data):

        body = json.dumps(data).encode("utf-8")



        self.send_response(status_code)

        self.send_header("Content-Type", "application/json")

        self.send_header("Content-Length", str(len(body)))

        self.send_header("Cache-Control", "no-store")

        self.end_headers()



        self.wfile.write(body)

    def admin_cookie(self):
        from http.cookies import SimpleCookie
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie["bluenode_admin"].value if "bluenode_admin" in cookie else None
        except Exception:
            return None

    def require_admin(self, csrf=False):
        token = self.admin_cookie()
        if ADMIN.authenticate(token) is None:
            ADMIN.audit("authorization", "rejected")
            self.send_json(401, {"ok": False, "error": "Remote Admin authentication required"})
            return False
        if csrf and not ADMIN.csrf_valid(token, self.headers.get("X-CSRF-Token")):
            ADMIN.audit("csrf", "rejected")
            self.send_json(403, {"ok": False, "error": "Invalid CSRF token"})
            return False
        return True

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY_BYTES:
                return None
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def send_admin_cookie(self, token, clear=False):
        config = _safe_config()
        parts = [f"bluenode_admin={'' if clear else token}", "Path=/", "HttpOnly",
                 "SameSite=Strict", f"Max-Age={0 if clear else config['session_seconds']}"]
        if config.get("secure_cookie", True):
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))



    def do_POST(self):

        path = self.path.split("?", 1)[0]
        if path == "/api/admin/login":
            payload = self.read_json()
            if not isinstance(payload, dict) or set(payload) - {"username", "password"}:
                self.send_json(400, {"ok": False, "error": "Invalid authentication request"})
                return
            status, result, token = ADMIN.login(payload.get("username", ""),
                                                payload.get("password", ""),
                                                self.client_address[0])
            if token:
                body = json.dumps(result).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_admin_cookie(token)
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_json(status, result)
            return

        if path == "/api/admin/logout":
            if not self.require_admin(csrf=True):
                return
            ADMIN.logout(self.admin_cookie())
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_admin_cookie("", clear=True)
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/admin/action":
            if not self.require_admin(csrf=True):
                return
            payload = self.read_json()
            if not isinstance(payload, dict):
                self.send_json(400, {"ok": False, "error": "Invalid JSON request"})
                return
            status, result = ADMIN.action(str(payload.get("action", "")), payload)
            self.send_json(status, result)
            return

        prefix = "/api/control/"



        if not path.startswith(prefix):

            self.send_json(404, {

                "ok": False,

                "error": "Unknown API endpoint"

            })

            return



        if _safe_config()["enabled"] and not self.require_admin(csrf=True):
            return

        action = path[len(prefix):].strip("/")

        if action in ("maintenance-enable", "maintenance-disable"):
            enabled = action == "maintenance-enable"
            state = automation.set_maintenance(enabled)
            self.send_json(200, {
                "ok": True,
                "action": action,
                "message": "Maintenance mode enabled" if enabled else "Maintenance mode disabled",
                "automation": state,
            })
            return



        # Manual AllStar node connect/disconnect

        if action in ("node-connect", "node-disconnect"):

            try:

                content_length = int(self.headers.get("Content-Length", "0"))

                raw_body = self.rfile.read(content_length)

                payload = json.loads(raw_body.decode("utf-8") or "{}")

            except (ValueError, json.JSONDecodeError):

                self.send_json(400, {

                    "ok": False,

                    "error": "Invalid JSON request"

                })

                return



            node_number = str(payload.get("node", "")).strip()



            # Allow normal AllStar node numbers only; no shell characters.

            if not node_number.isdigit() or not (1 <= len(node_number) <= 10):

                self.send_json(400, {

                    "ok": False,

                    "error": "Enter a valid numeric AllStar node number"

                })

                return



            local_node = str(CONFIG.get("node", "")).strip()



            if not local_node.isdigit():

                self.send_json(500, {

                    "ok": False,

                    "error": "Local node number is not configured correctly"

                })

                return



            dtmf = "*3" if action == "node-connect" else "*1"

            rpt_command = f"rpt fun {local_node} {dtmf}{node_number}"



            try:

                result = subprocess.run(

                    ["sudo", "-n", "asterisk", "-rx", rpt_command],

                    capture_output=True,

                    text=True,

                    timeout=15,

                )

            except subprocess.TimeoutExpired:

                self.send_json(504, {

                    "ok": False,

                    "action": action,

                    "node": node_number,

                    "error": "Asterisk command timed out"

                })

                return

            except OSError as exc:

                self.send_json(500, {

                    "ok": False,

                    "action": action,

                    "node": node_number,

                    "error": str(exc)

                })

                return



            if result.returncode != 0:

                self.send_json(500, {

                    "ok": False,

                    "action": action,

                    "node": node_number,

                    "error": result.stderr.strip() or result.stdout.strip() or

                             f"Command exited with status {result.returncode}"

                })

                return



            event_name = "CONTROL." + action.replace("-", ".").upper()

            verb = "Connect" if action == "node-connect" else "Disconnect"



            emit(

                event_name,

                f"{verb} command sent for node {node_number}"

            )



            self.send_json(200, {

                "ok": True,

                "action": action,

                "node": node_number,

                "message": f"{verb} command sent for node {node_number}"

            })

            return



        # Existing fixed dashboard controls

        command = ACTIONS.get(action)



        if command is None:

            self.send_json(403, {

                "ok": False,

                "error": "Action not permitted"

            })

            return



        try:

            result = subprocess.run(

                ["sudo", "-n", command],

                capture_output=True,

                text=True,

                timeout=15,

            )



        except subprocess.TimeoutExpired:

            self.send_json(504, {

                "ok": False,

                "action": action,

                "error": "Command timed out"

            })

            return



        except OSError as exc:

            self.send_json(500, {

                "ok": False,

                "action": action,

                "error": str(exc)

            })

            return



        if result.returncode != 0:

            self.send_json(500, {

                "ok": False,

                "action": action,

                "error": result.stderr.strip() or result.stdout.strip() or

                         f"Command exited with status {result.returncode}"

            })

            return



        event_name = "CONTROL." + action.replace("-", ".").upper()



        emit(

            event_name,

            "Dashboard action completed"

        )



        self.send_json(200, {

            "ok": True,

            "action": action,

            "message": result.stdout.strip()

        })




if __name__ == "__main__":

    server = ThreadingHTTPServer((HOST, PORT), NodeSmartHandler)



    print(f"BlueNode web server listening on {HOST}:{PORT}")



    try:

        server.serve_forever()

    except KeyboardInterrupt:

        pass

    finally:

        server.server_close()
