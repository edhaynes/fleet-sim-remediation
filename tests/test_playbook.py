"""Runs the playbooks against tests/fake_sim_api.py. Needs ansible-playbook on PATH.

    python3 -m unittest discover -s tests
"""
import os
import socket
import subprocess
import sys
import time
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TOKEN = "unit-test-token-0123456789abcdef"  # pragma: allowlist secret
PLAYBOOK = os.path.join(ROOT, "playbooks", "remediate.yml")
SINGLE = {name: os.path.join(ROOT, "playbooks", name + ".yml") for name in ("restart_host", "reconnect_host", "reapply_config")}
ENV = dict(os.environ, ANSIBLE_LOCALHOST_WARNING="False", ANSIBLE_INVENTORY_UNPARSED_WARNING="False",
           ANSIBLE_NOCOLOR="1")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Playbook(unittest.TestCase):
    def setUp(self):
        self.port = free_port()
        self.server = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "fake_sim_api.py"), str(self.port), TOKEN])
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    def tearDown(self):
        self.server.terminate()
        self.server.wait()

    def run_playbook(self, *extra, playbook=PLAYBOOK):
        cmd = ["ansible-playbook", playbook, "-e", "fleetsim_api_url=http://127.0.0.1:%d" % self.port,
               "-e", "fleetsim_api_token=" + TOKEN] + list(extra)
        p = subprocess.run(cmd, env=ENV, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout + p.stderr

    def test_repairs_each_host_with_the_right_action(self):
        rc, out = self.run_playbook("-e", '{"target_clusters": ["c1", "c2"]}')
        self.assertEqual(rc, 0, out)
        self.assertIn("restart h1", out)
        self.assertIn("reconnect h2", out)
        self.assertNotIn("h3", out.split("Report what will be repaired")[1].split("TASK")[0])

    def test_token_never_in_output_even_verbose(self):
        # Regression (2026-10-21): looping over the registered POST results printed the
        # Authorization header in later tasks, despite no_log on the request itself.
        for verbosity in ([], ["-vvv"]):
            rc, out = self.run_playbook("-e", '{"target_clusters": ["c1"]}', *verbosity)
            self.assertEqual(rc, 0, out)
            self.assertIn("restart h1", out)        # the repairs really ran
            self.assertNotIn(TOKEN, out, "token leaked at verbosity %s" % (verbosity or "default"))

    def test_nothing_to_repair(self):
        rc, out = self.run_playbook("-e", '{"target_clusters": ["c2"]}')
        self.assertEqual(rc, 0, out)
        self.assertIn("nothing to repair", out)

    def test_requires_target_clusters(self):
        rc, out = self.run_playbook()
        self.assertNotEqual(rc, 0)
        self.assertIn("target_clusters", out)

    def test_runbook_repairs_misconfigured_with_reapply(self):
        rc, out = self.run_playbook("-e", '{"target_clusters": ["c3"]}')
        self.assertEqual(rc, 0, out)
        self.assertIn("reapply_config h4", out)

    def test_ai_hands_off_and_repairs_nothing(self):
        url = "fleetsim_advisor_url=http://127.0.0.1:%d" % self.port
        rc, out = self.run_playbook("-e", '{"target_clusters": ["c1", "c2"], "fleetsim_remediation": "ai"}', "-e", url)
        self.assertEqual(rc, 0, out)
        self.assertIn("handed to the AI advisor: c1, proposal rp-c1-h1,h2", out)
        self.assertNotIn("proposal rp-c2", out)          # c2 has nothing down: no incident
        self.assertNotIn("Request restart", out)        # nothing repaired here

    def test_ai_needs_the_advisor_url(self):
        rc, out = self.run_playbook("-e", '{"target_clusters": ["c1"], "fleetsim_remediation": "ai"}')
        self.assertNotEqual(rc, 0)
        self.assertIn("fleetsim_advisor_url", out)

    def test_unknown_mode(self):
        rc, out = self.run_playbook("-e", '{"target_clusters": ["c1"], "fleetsim_remediation": "magic"}')
        self.assertNotEqual(rc, 0)
        self.assertIn("runbook or ai", out)

    def test_single_action_playbooks(self):
        for name, host, action in [("restart_host", "h1", "restart"), ("reconnect_host", "h2", "reconnect"),
                                   ("reapply_config", "h4", "reapply_config")]:
            rc, out = self.run_playbook("-e", "target_host=" + host, playbook=SINGLE[name])
            self.assertEqual(rc, 0, out)
            self.assertIn("%s %s (running)" % (action, host), out)
            self.assertIn("%s: %s is ok" % (host, host), out)

    def test_single_action_refuses_a_ready_or_missing_host(self):
        rc, out = self.run_playbook("-e", "target_host=h3", playbook=SINGLE["restart_host"])
        self.assertNotEqual(rc, 0)
        self.assertIn("nothing to repair", out)
        rc, out = self.run_playbook("-e", "target_host=nope", playbook=SINGLE["restart_host"])
        self.assertNotEqual(rc, 0)
        self.assertIn("404", out)
        rc, out = self.run_playbook(playbook=SINGLE["restart_host"])
        self.assertNotEqual(rc, 0)
        self.assertIn("target_host", out)

    def test_an_action_the_simulator_refuses_fails_the_job(self):
        # restart doesn't apply to an isolated host: the Sim API answers 409 and the job must fail
        rc, out = self.run_playbook("-e", "target_host=h2", playbook=SINGLE["restart_host"])
        self.assertNotEqual(rc, 0)
        self.assertIn("Request restart on h2", out)
        self.assertNotIn(TOKEN, out)

    def test_token_never_in_output_any_playbook(self):
        url = "fleetsim_advisor_url=http://127.0.0.1:%d" % self.port
        runs = [((("-e", '{"target_clusters": ["c1"], "fleetsim_remediation": "ai"}', "-e", url)), PLAYBOOK)]
        runs += [(("-e", "target_host=h1"), SINGLE["restart_host"])]
        for extra, playbook in runs:
            for verbosity in ([], ["-vvv"]):
                rc, out = self.run_playbook(*extra, *verbosity, playbook=playbook)
                self.assertEqual(rc, 0, out)
                self.assertNotIn(TOKEN, out, "token leaked: %s %s" % (os.path.basename(playbook), verbosity or "default"))


if __name__ == "__main__":
    unittest.main()
