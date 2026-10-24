"""A tiny stand-in for a fleet-sim Sim API v1, for testing the playbook. Stdlib only.

    python3 tests/fake_sim_api.py PORT TOKEN

Clusters: c1 with h1 (failed) and h2 (isolated), c2 with h3 (ok), c3 with h4 (misconfigured).
Actions finish on the second poll. Also stands in for the AI advisor (POST /v1/incidents). Writes
need `Authorization: Bearer TOKEN`.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOSTS = {"h1": ("c1", "failed"), "h2": ("c1", "isolated"), "h3": ("c2", "ok"), "h4": ("c3", "misconfigured")}
SIMULATOR = {"actions": [
    {"id": "restart", "applies_to": ["failed", "offline", "degraded"]},
    {"id": "reconnect", "applies_to": ["isolated"]},
    {"id": "reapply_config", "applies_to": ["misconfigured"]},
]}
ACTIONS = {}


def host(h):
    cluster, status = HOSTS[h]
    return {"id": h, "cluster_id": cluster, "status": status, "ready": status in ("ok", "degraded")}


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
            return self.send(200, [host(h) for h, (c, _) in HOSTS.items() if c == cluster])
        if self.path.startswith("/v1/hosts/"):
            h = self.path.rsplit("/", 1)[1]
            return self.send(200, host(h)) if h in HOSTS else self.send(404, {"error": "not_found"})
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
        if self.path == "/v1/incidents":
            return self.send(202, {"cluster": body["cluster"], "proposal": "rp-%s-%s" % (body["cluster"], ",".join(body["hosts"]))})
        kind = next((a for a in SIMULATOR["actions"] if a["id"] == body["action"]), None)
        if kind is None or HOSTS[body["target_id"]][1] not in kind["applies_to"]:
            return self.send(409, {"error": "conflict"})
        aid = "a-%06d" % (len(ACTIONS) + 1)
        ACTIONS[aid] = {"id": aid, "target_id": body["target_id"], "action": body["action"],
                        "state": "running", "message": "started", "polls": 0}
        self.send(202, {k: v for k, v in ACTIONS[aid].items() if k != "polls"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    Handler.token = sys.argv[2]
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
