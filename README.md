# fleet-sim-remediation

Generic Ansible playbooks that repair **simulated** hosts through a fleet-sim Sim API (v1).
It's the AAP half of a closed-loop demo: Red Hat Advanced Cluster Management detects a
non-compliant cluster, its `PolicyAutomation` launches this playbook as an Ansible Automation
Platform job, and the playbook asks the simulator to repair the hosts that aren't ready.

Everything it touches is simulated. It changes no real systems, and contains no hostnames or
credentials: you supply those when you run it.

## What it does

`playbooks/remediate.yml`, the runbook ACM launches:

1. Reads the simulator's repair actions (`GET /v1/simulator`).
2. Lists the hosts of each cluster in `target_clusters` and keeps the ones not ready.
3. With `fleetsim_remediation: runbook` (the default): for each host, requests the action that
   applies to its status (`POST /v1/actions`, with the token), one host at a time, waits for it
   and fails if it didn't succeed.
4. With `fleetsim_remediation: ai`: repairs nothing; posts each cluster's incident to a fleet-sim
   AI advisor (`POST {fleetsim_advisor_url}/v1/incidents`, same token), which suggests one of the
   playbooks below for a person to approve.

The single-action playbooks, which an AI advisor may suggest (each runs one Sim API action on
`target_host`, or on `target_cluster` for a cluster-scope action, and refuses a target that is
already ready):

| Playbook | Sim API action | Target |
|---|---|---|
| `playbooks/restart_host.yml` | `restart` | `target_host` |
| `playbooks/reconnect_host.yml` | `reconnect` | `target_host` |
| `playbooks/reapply_config.yml` | `reapply_config` | `target_host` |
| `playbooks/restore_uplink.yml` | `restore_uplink` (cluster scope, Sim API 1.2.0) | `target_cluster` |

The runbook (`remediate.yml`) only ever picks host actions; a cluster-scope action is left for a
person or the AI advisor to choose.

All of them call the Sim API through one role, `playbooks/roles/sim_action`.

## Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `fleetsim_api_url` | yes | — | Sim API base URL |
| `fleetsim_api_token` | yes | — | bearer token for writes; supply it as an AAP credential |
| `target_clusters` | `remediate.yml` | `[]` | cluster ids; ACM PolicyAutomation passes the violating clusters |
| `target_host` | host single-action playbooks | — | the host to act on |
| `target_cluster` | `restore_uplink.yml` | — | the cluster to act on |
| `fleetsim_approval` | no | — | added to the action's `requested_by`, e.g. "AI proposal rp-1 approved by alice" |
| `fleetsim_remediation` | no | `runbook` | `runbook` or `ai` (`remediate.yml`) |
| `fleetsim_advisor_url` | for `ai` | — | the AI advisor's base URL |
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

The tests run the playbooks against `tests/fake_sim_api.py` (stdlib; it also stands in for the
advisor) on ansible-core 2.16, the version in AAP 2.5-2.7 execution environments. They check each
host gets the right action, the AI hand-off repairs nothing, an action the simulator refuses fails
the job, the no-op and missing-input cases, and that the token never appears in the output, at
default verbosity and at `-vvv`, for every playbook.

## License

Apache-2.0
