# AgenticNetworks governance

A working demo of **multi-repo policy governance with [Nornyx](https://github.com/mazinmarji/nornyx)**.

One canonical policy (`SafeDeliveryPolicy`) is declared once in
[`nornyx.workspace.yaml`](nornyx.workspace.yaml) and enforced across every service
contract under [`services/`](services). Two CI jobs keep it honest:

- **[workspace.yml](.github/workflows/workspace.yml)** — on every push/PR, runs
  `nornyx workspace-check`. If any service's policy diverges from the canonical
  set, the build fails (exit 1) and names the exact rule.
- **[policy-sync.yml](.github/workflows/policy-sync.yml)** — weekly (and on
  demand), runs `nornyx workspace-check --write` to *propagate* the canonical
  policy into each service and opens a PR with the changes. You edit the policy in
  one place (the manifest); a human approves the PR.

## Why this exists

A single `.nyx` is the source of truth *within* one repo, but each repo can carry
a divergent copy of the "same" org policy and still pass its own drift gate. This
repo is the layer *above* the services: it makes the org standard a checked
artifact, not a convention. See [org-governance/FINDINGS.md](org-governance/FINDINGS.md)
for the adversarial test that motivated it, and the
[case study](https://github.com/mazinmarji/nornyx/blob/main/docs/CASE_STUDY_multi_repo_governance.md)
for the full arc.

## Try it

```bash
pip install nornyx
nornyx workspace-check --manifest nornyx.workspace.yaml          # verify
nornyx workspace-check --manifest nornyx.workspace.yaml --write  # propagate
```

## Services

| Service | Contract | Standalone repo |
|---------|----------|-----------------|
| GovFlags | [services/govflags.nyx](services/govflags.nyx) | [mazinmarji/govflags](https://github.com/mazinmarji/govflags) |
| NotifySvc | [services/notify.nyx](services/notify.nyx) | — (contract-only) |

The contracts here are governed copies; each service edits its own behaviour, but
`SafeDeliveryPolicy` is owned by this workspace.
