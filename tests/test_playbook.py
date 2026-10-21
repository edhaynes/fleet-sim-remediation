"""Runs playbooks/remediate.yml against tests/fake_sim_api.py. Needs ansible-playbook on PATH.

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

    def run_playbook(self, *extra):
        cmd = ["ansible-playbook", PLAYBOOK, "-e", "fleetsim_api_url=http://127.0.0.1:%d" % self.port,
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


if __name__ == "__main__":
    unittest.main()
