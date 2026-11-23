"""Safe fast-forward updates for source checkouts."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_URL = "https://github.com/flakeshuz/CerealBox.git"
MAIN_REF = "refs/heads/main"
GIT_TIMEOUT_SECONDS = 12


class UpdateError(RuntimeError):
    """An update cannot be checked or applied safely."""


@dataclass(frozen=True)
class UpdateStatus:
    current_sha: str
    latest_sha: str
    has_local_changes: bool

    @property
    def available(self) -> bool:
        return self.current_sha != self.latest_sha


def _git(root: Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UpdateError("Git is required to update this source checkout.") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpdateError("Git timed out while checking or applying the update.") from exc
    if result.returncode:
        detail = result.stderr.strip()
        raise UpdateError(detail or "Git could not complete the update operation.")
    return result.stdout.strip()


def _verify_checkout(root: Path) -> None:
    if not (root / ".git").exists():
        raise UpdateError("Updates are available only from a Git source checkout.")
    checkout = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if checkout != root.resolve():
        raise UpdateError("Updates are available only from a Git source checkout.")
    remote = _git(root, "remote", "get-url", "origin").strip()
    normalized = remote.lower()
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized.removeprefix("git@github.com:")
    elif normalized.startswith("ssh://git@github.com/"):
        normalized = "https://github.com/" + normalized.removeprefix("ssh://git@github.com/")
    normalized = normalized.removesuffix(".git").rstrip("/")
    expected = REPOSITORY_URL.removesuffix(".git").lower()
    if normalized != expected:
        raise UpdateError("The Git origin is not the CerealBox repository.")


def check_for_updates(root: Path) -> UpdateStatus:
    root = Path(root)
    _verify_checkout(root)
    current = _git(root, "rev-parse", "HEAD")
    remote = _git(root, "ls-remote", REPOSITORY_URL, MAIN_REF)
    fields = remote.split()
    if (
        len(fields) != 2
        or fields[1] != MAIN_REF
        or not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", fields[0])
    ):
        raise UpdateError("GitHub did not return a valid main-branch commit.")
    changes = _git(root, "status", "--porcelain", "--untracked-files=normal")
    return UpdateStatus(current, fields[0].lower(), bool(changes))


def apply_update(root: Path, expected_sha: str) -> str:
    root = Path(root)
    status = check_for_updates(root)
    if status.has_local_changes:
        raise UpdateError("Commit or stash local changes before updating.")
    if not status.available:
        raise UpdateError("CerealBox is already up to date.")
    if status.latest_sha != expected_sha.lower():
        raise UpdateError("The main branch changed since the update check. Check again.")

    _git(root, "fetch", "--quiet", "origin", "main")
    fetched = _git(root, "rev-parse", "FETCH_HEAD")
    if fetched.lower() != expected_sha.lower():
        raise UpdateError("The main branch changed while downloading. Check again.")
    with tempfile.TemporaryDirectory(prefix="cerealbox-update-hooks-") as hooks:
        _git(root, "-c", f"core.hooksPath={hooks}", "merge", "--ff-only", "--no-edit", "FETCH_HEAD")
    return _git(root, "rev-parse", "HEAD")
