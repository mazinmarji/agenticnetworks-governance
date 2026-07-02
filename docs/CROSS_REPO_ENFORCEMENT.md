# Cross-repo enforcement

How the canonical `SafeDeliveryPolicy` declared in
[`nornyx.workspace.yaml`](../nornyx.workspace.yaml) reaches the **real** service
repositories — not just the governed copies in this repo.

## The problem this closes

`nornyx workspace-check` here verifies the copies under [`services/`](../services)
match the canonical policy. But the services actually *ship* from their own repos
([mazinmarji/govflags](https://github.com/mazinmarji/govflags),
[mazinmarji/notify](https://github.com/mazinmarji/notify)). Without a link, each
service repo could carry a divergent copy of the "same" org policy and still pass
its own within-repo drift gate — exactly the cross-repo gap described in
[`org-governance/FINDINGS.md`](../org-governance/FINDINGS.md).

## Two layers of enforcement

1. **Inside this repo (central view + authoritative live check).**
   [`workspace.yml`](../.github/workflows/workspace.yml) has two jobs:
   - `workspace-check` runs `nornyx workspace-check` over the governed copies
     under [`services/`](../services) — a central *view* of the policy.
   - `live-members` runs [`scripts/verify_live_members.py`](../scripts/verify_live_members.py),
     which fetches each member's **live** contract from its shipping repo
     (mapped in [`services/member-sources.yaml`](../services/member-sources.yaml))
     and fails if that live contract no longer resolves to the canonical policy.
     This closes the copy-vs-reality gap: the central copies are only a view, so
     a member repo that diverged — or quietly dropped its own conformance CI —
     is now caught from the center too. It also fails closed if a declared member
     is missing a source mapping, so onboarding a member and verifying it live
     stay coupled.

   [`policy-sync.yml`](../.github/workflows/policy-sync.yml) propagates the
   canonical policy into the local copies and opens a PR.

2. **Inside each service repo (live, pull-based).** Each service repo runs
   `scripts/policy_conformance.py`, which:
   - fetches **this** repo's `nornyx.workspace.yaml` over its public raw URL —
     the single source of truth, never copied;
   - builds a one-member manifest pointing at that repo's own contract;
   - runs `nornyx workspace-check`.

   Its **CI** runs this in verify mode on every push/PR (fails on divergence);
   its **`policy-sync.yml`** runs it weekly with `--write`, regenerates the
   control artifacts, and opens a same-repo PR.

```
        nornyx.workspace.yaml  (canonical SafeDeliveryPolicy — ONE source)
                 │  (fetched live over raw URL; never copied into services)
   ┌─────────────┼─────────────┐
   ▼             ▼             ▼
 govflags      notify     (next service)
 CI verify     CI verify
 weekly sync   weekly sync   ──►  same-repo PR  ──►  human approves
```

## Why pull-based (and not a central push)

A central job pushing into other repos would need a cross-repo write token. The
pull model uses **only each repo's own `GITHUB_TOKEN`** for its same-repo sync PR
— least privilege, no shared secret. The canonical policy is fetched fresh each
run, so there is no second copy in the service repos to drift.

## The loop, end to end

1. Change `SafeDeliveryPolicy` once, here, in `nornyx.workspace.yaml`.
2. Every service repo's next CI run (or weekly sync) detects the change.
3. Verify-mode CI fails loudly; sync-mode opens a PR that updates the contract and
   regenerates artifacts.
4. A human reviews and merges each PR. **AI is a delivery surface, never the
   approver.**
