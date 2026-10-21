# fleet-sim-remediation

A generic Ansible playbook that repairs **simulated** hosts through a fleet-sim Sim API (v1).
It's the AAP half of a closed-loop demo: Red Hat Advanced Cluster Management detects a
non-compliant cluster, its `PolicyAutomation` launches this playbook as an Ansible Automation
Platform job, and the playbook asks the simulator to repair the hosts that aren't ready.

Everything it touches is simulated. It changes no real systems, and contains no hostnames or
credentials: you supply those when you run it.

## What it does

1. Reads the simulator's repair actions (`GET /v1/simulator`).
2. Lists the hosts of each cluster in `target_clusters` and keeps the ones not ready.
3. For each, requests the action that applies to its status (`POST /v1/actions`, with the token).
4. Waits for every action to finish and fails if one didn't succeed.

## Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `fleetsim_api_url` | yes | — | Sim API base URL |
| `fleetsim_api_token` | yes | — | bearer token for writes; supply it as an AAP credential |
| `target_clusters` | yes | `[]` | cluster ids; ACM PolicyAutomation passes the violating clusters |
| `fleetsim_action_timeout_seconds` | no | `300` | how long to wait for each repair |
| `fleetsim_validate_certs` | no | `true` | verify TLS |

## Run it

From AAP: a project pointing at this repository, a job template running
`playbooks/remediate.yml` on a localhost inventory, a credential that injects
`fleetsim_api_token`, and `fleetsim_api_url` in the template's extra variables.

By hand (ansible-core 2.15 or later):

```bash
ansible-playbook playbooks/remediate.yml \
  -e fleetsim_api_url=http://localhost:7340 -e fleetsim_api_token="$FLEETSIM_API_TOKEN" \
  -e '{"target_clusters": ["closet-a01-cluster"]}'
```

## Tests

```bash
python3 -m venv .venv && .venv/bin/python3 -m pip install -r requirements-dev-lock.txt
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python3 -m unittest discover -s tests
```

The tests run the playbook against `tests/fake_sim_api.py` (stdlib) on ansible-core 2.16, the
version in AAP 2.5-2.7 execution environments. They check each host gets the right action, the
no-op and missing-input cases, and that the token never appears in the output, at default
verbosity and at `-vvv`.

## License

Apache-2.0
