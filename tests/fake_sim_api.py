"""A tiny stand-in for a fleet-sim Sim API v1, for testing the playbook. Stdlib only.

    python3 tests/fake_sim_api.py PORT TOKEN

Two clusters: c1 with h1 (failed) and h2 (isolated), c2 with h3 (ok). Actions finish on the
second poll. Writes need `Authorization: Bearer TOKEN`.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOSTS = {"h1": ("c1", "failed"), "h2": ("c1", "isolated"), "h3": ("c2", "ok")}
SIMULATOR = {"actions": [
    {"id": "restart", "applies_to": ["failed", "offline", "degraded"]},
    {"id": "reconnect", "applies_to": ["isolated"]},
]}
ACTIONS = {}


class Handler(BaseHTTPRequestHandler):
    token = ""

    def send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/v1/simulator":
            return self.send(200, SIMULATOR)
        if self.path.startswith("/v1/hosts?cluster="):
            cluster = self.path.split("=", 1)[1]
            return self.send(200, [{"id": h, "status": s, "ready": s in ("ok", "degraded")}
                                   for h, (c, s) in HOSTS.items() if c == cluster])
        if self.path.startswith("/v1/actions/"):
            a = ACTIONS[self.path.rsplit("/", 1)[1]]
            a["polls"] += 1
            if a["polls"] >= 2:
                a.update(state="succeeded", message="%s is ok" % a["target_id"])
            return self.send(200, {k: v for k, v in a.items() if k != "polls"})
        self.send(404, {"error": "not_found"})

    def do_POST(self):
        if self.headers.get("Authorization") != "Bearer " + self.token:
            return self.send(401, {"error": "unauthorized"})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        aid = "a-%06d" % (len(ACTIONS) + 1)
        ACTIONS[aid] = {"id": aid, "target_id": body["target_id"], "action": body["action"],
                        "state": "running", "message": "started", "polls": 0}
        self.send(202, {k: v for k, v in ACTIONS[aid].items() if k != "polls"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    Handler.token = sys.argv[2]
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
