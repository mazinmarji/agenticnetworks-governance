#!/usr/bin/env python3
"""Central, live verification that every workspace member SHIPS a conformant contract.

`workspace.yml` runs `nornyx workspace-check` over the local copies under
`services/` — a central *view*. This script closes the remaining gap: it verifies
the **live** contracts in the member repositories themselves resolve to the
canonical `SafeDeliveryPolicy`, from the center, on every push.

For each member declared in `nornyx.workspace.yaml` (mapped to its shipping repo
via `services/member-sources.yaml`) it:
  1. fetches the member's live contract from its default branch (raw URL),
  2. fetches any file the contract `ref:`s (its vendored canonical policy),
  3. runs `nornyx workspace-check` on the live contract with the canonical
     policy from THIS repo's manifest — failing if the live contract resolves to
     anything other than canonical.

Fails closed: a member with no source mapping, an unreachable repo, a missing
contract, or a divergent policy all exit non-zero. Read-only (GET only); no
token needed (public raw URLs).
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "nornyx.workspace.yaml"
SOURCES = ROOT / "services" / "member-sources.yaml"
RAW = "https://raw.githubusercontent.com/{repo}/{branch}/{path}"
_REF_RE = re.compile(r"^\s*ref:\s*([^#\s]+)#", re.MULTILINE)


def _fetch(repo: str, path: str, branch: str = "main") -> str:
    url = RAW.format(repo=repo, branch=branch, path=path)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (public GitHub raw)
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    # raw.githubusercontent.com can 404 for seconds after a member merges (CDN
    # lag). The contents API is fresh immediately — fall back to it so a member's
    # first post-merge run isn't a false failure.
    api = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    req = urllib.request.Request(  # noqa: S310 (public GitHub API)
        api, headers={"Accept": "application/vnd.github+json", "User-Agent": "agenticnetworks-governance"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8"))
    return base64.b64decode(payload["content"]).decode("utf-8")


def _verify_member(member_path: str, source: dict, canonical: dict) -> list[str]:
    """Return a list of failure messages for one member (empty == conformant)."""
    repo = source.get("repo")
    contract_path = source.get("contract")
    if not repo or not contract_path:
        return [f"{member_path}: source mapping needs both 'repo' and 'contract'"]

    try:
        contract_text = _fetch(repo, contract_path)
    except urllib.error.HTTPError as exc:
        return [f"{member_path}: live contract {repo}/{contract_path} -> HTTP {exc.code}"]
    except (urllib.error.URLError, OSError) as exc:
        return [f"{member_path}: cannot reach {repo}/{contract_path}: {exc}"]

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        contract_name = Path(contract_path).name
        (tmpdir / contract_name).write_text(contract_text, encoding="utf-8")

        # Fetch every file the live contract references (its vendored policy).
        # A `ref:` target is relative to the CONTRACT's directory in the repo
        # (e.g. apps/backend/contracts/org-policy.yaml), so resolve it there — not
        # at repo root — then write it flat beside the contract in the temp dir.
        contract_dir = PurePosixPath(contract_path).parent
        for ref_file in sorted(set(_REF_RE.findall(contract_text))):
            ref_repo_path = str(contract_dir / ref_file)
            try:
                (tmpdir / Path(ref_file).name).write_text(_fetch(repo, ref_repo_path), encoding="utf-8")
            except (urllib.error.URLError, OSError) as exc:
                return [f"{member_path}: contract refs '{ref_file}' but {repo}/{ref_repo_path} is unreachable: {exc}"]

        # Check the live contract against THIS repo's canonical policy.
        manifest = {
            "workspace": canonical.get("workspace", "AgenticNetworks"),
            "policies": canonical["policies"],
            "members": [{"path": contract_name}],
        }
        (tmpdir / "live-check.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "-m", "nornyx.cli", "workspace-check", "--manifest", "live-check.yaml"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stdout + result.stderr).strip().splitlines()
            tail = detail[-1] if detail else "workspace-check failed"
            return [f"{member_path}: live contract at {repo}/{contract_path} diverges from canonical — {tail}"]
    return []


def main() -> int:
    canonical = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    declared = [str(m["path"]) for m in canonical.get("members", []) if isinstance(m, dict) and m.get("path")]
    sources = (yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}).get("members", {})

    failures: list[str] = []
    for member_path in declared:
        source = sources.get(member_path)
        if not source:
            failures.append(f"{member_path}: declared in the manifest but missing from services/member-sources.yaml")
            continue
        failures.extend(_verify_member(member_path, source, canonical))

    # A source mapping for a repo that is no longer a member is dead config.
    for extra in set(sources) - set(declared):
        failures.append(f"{extra}: in member-sources.yaml but not a member in nornyx.workspace.yaml")

    if failures:
        print("Live member verification FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"Live member verification passed: {len(declared)} member(s) ship a contract that resolves to canonical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
