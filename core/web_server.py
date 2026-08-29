
#!/usr/bin/env python3



import json

import subprocess

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from pathlib import Path

from event_logger import emit
from config import load_config



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



    def send_json(self, status_code, data):

        body = json.dumps(data).encode("utf-8")



        self.send_response(status_code)

        self.send_header("Content-Type", "application/json")

        self.send_header("Content-Length", str(len(body)))

        self.send_header("Cache-Control", "no-store")

        self.end_headers()



        self.wfile.write(body)



    def do_POST(self):

        prefix = "/api/control/"



        if not self.path.startswith(prefix):

            self.send_json(404, {

                "ok": False,

                "error": "Unknown API endpoint"

            })

            return



        action = self.path[len(prefix):].strip("/")



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



    print(f"NodeSmart web server listening on {HOST}:{PORT}")



    try:

        server.serve_forever()

    except KeyboardInterrupt:

        pass

    finally:

        server.server_close()
