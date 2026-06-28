# Adversarial test: does Nornyx keep policy consistent across repos?

Two governed apps — [GovFlags](../services/govflags.nyx) and
[NotifySvc](../services/notify.nyx) — share one org policy (`SafeDeliveryPolicy`).
We then evolved the standard and watched what each safety net caught.

## Setup
- Both repos carry an identical `SafeDeliveryPolicy` block in their `.nyx`.
- Both have a Nornyx within-repo drift gate (`scripts/check_drift.py`).
- An org-level checker (a throwaway prototype) compared each repo's policy to a
  canonical standard. **That checker was not part of Nornyx** — we had to build
  it, which is exactly what `nornyx workspace-check` (now native) replaced.

## What happened when the org changed the standard (in GovFlags only)

| Safety net | Caught the divergence? |
|------------|------------------------|
| GovFlags' own Nornyx drift gate | **No** — stayed green |
| NotifySvc's own Nornyx drift gate | **No** — stayed green |
| Org-level `check_org_policy.py` (non-Nornyx) | **Yes** — exit 1, named the exact rule |

## Two distinct gaps found

**Gap 1 — cross-repo (the expected one).** The `.nyx` language has no
`import`/`extends`/`policy-ref`: `include` is only context file-globs, and
`profiles` bake policy in at `init` then forget. So every repo owns a *copy* of
the org policy. Change it in one repo and the others have no idea — each still
passes its own gate because each is internally consistent. **Nornyx guarantees
within-repo consistency, not across-repo.** Closing this needs org-level tooling
that lives above the repos (what `check_org_policy.py` is).

**Gap 2 — within-repo, sharper and unexpected.** The drift gate recommended in
Nornyx's own `docs/USE_IN_YOUR_REPO.md` diffs **only `AGENTS.md`**. But
`AGENTS.md` does not render policy rules — they go to `policy.yaml`. So changing
a *policy rule* leaves `AGENTS.md` byte-identical and the gate passes green even
though `policy.yaml` changed. A correct within-repo gate must diff the **entire**
generated output directory, not just `AGENTS.md`. (Our per-repo `check_drift.py`
inherited this flaw and should be hardened to diff the whole `.nyx-out/`.)

## Verdict
The cross-repo consistency story **does not hold up out of the box.** Nornyx is a
strong *within-repo* single-source-of-truth + generator; multi-repo governance
requires an org layer Nornyx does not ship. That layer is small (≈70 lines here),
but it is real work, and the fact that both built-in gates stayed green during a
genuine policy divergence is exactly the false sense of safety to warn about.

### Product implications for Nornyx
1. Ship a first-class **org/workspace policy** the way it could be referenced
   (`policy-ref`/import) so repos link to one source instead of copying it.
2. Make the recommended drift gate diff the **whole** generated set, not just
   `AGENTS.md`; otherwise policy drift is invisible.

## Resolution (Nornyx v1.1.6)

Both gaps are now fixed in the public Nornyx release:

- **Gap 2** → `nornyx drift <contract> --out <dir>` compares every generated
  artifact by hash, so policy.yaml drift is caught. GovFlags' own gate, CI, and
  governance test were switched to it; verified it now catches a policy-only
  change the old AGENTS.md-only gate missed.
- **Gap 1** → `nornyx workspace-check --manifest nornyx.workspace.yaml` declares
  canonical policies once and verifies every member repo matches. The canonical
  policy lives in [../nornyx.workspace.yaml](../nornyx.workspace.yaml) and the
  member contracts under [../services/](../services).

`check_org_policy.py` here was the throwaway prototype that proved the gap; it is
**superseded by the native `nornyx workspace-check`** and kept only as a record
of what the gap looked like before the fix.

## Sync mode (Nornyx v1.1.7)

`workspace-check` started as match-only enforcement (catches divergence but you
still hand-copy the policy into each repo). v1.1.7 adds **`--write` sync mode**:
the canonical policy is edited once in the manifest and *propagated* into every
member contract surgically (only the matched policy's rule block is rewritten;
comments and other blocks are preserved; members stay `nornyx check`-valid). This
gives true single-source-at-authoring without a language-level `policy-ref` —
avoiding reopening the frozen v1.0 schema or adding cross-repo file resolution.
The remaining (deliberate) limit: members still each carry a *resolved copy*, so
a contract is auditable on its face; they reference the manifest at sync time,
not at read time.
