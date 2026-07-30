#!/usr/bin/env python3
"""Synchronize Mobilint's managed Codex review caller through pull requests."""

from __future__ import annotations

import argparse
import base64
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


API_VERSION = "2026-03-10"
CALLER_PATH = ".github/workflows/code-review.yml"
AUTOMATION_BRANCH = "automation/sync-codex-review"
PR_TITLE = "chore(actions): synchronize Codex review caller"
COMMIT_MESSAGE = "chore(actions): synchronize Codex review caller"
MANAGED_PREFIX = (
    "# managed-by: mobilint/.github\n"
    "# managed-template: code-review\n"
)
REPOSITORY_RE = re.compile(r"^mobilint/[A-Za-z0-9._-]+$")
BRANCH_RE = re.compile(
    r"^(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]+(?<![/.])$"
)


class SyncError(RuntimeError):
    """A recoverable synchronization failure for one repository."""


@dataclass(frozen=True)
class RepositoryConfig:
    """One manifest entry."""

    name: str
    enabled: bool
    adopt_existing: bool
    profile: str = "default"
    overrides: dict[str, Any] | None = None


@dataclass
class SyncResult:
    """Machine-readable result for one repository."""

    repository: str
    status: str
    default_branch: str = ""
    classification: str = ""
    changed: bool = False
    pull_request_url: str = ""
    message: str = ""


class RepositoryService(Protocol):
    """GitHub operations required by the synchronizer."""

    def repository(self, name: str) -> dict[str, Any]: ...

    def actions_enabled(self, name: str) -> bool: ...

    def branch_sha(self, name: str, branch: str) -> str | None: ...

    def create_branch(self, name: str, branch: str, sha: str) -> None: ...

    def file_content(self, name: str, path: str, branch: str) -> tuple[str, str] | None: ...

    def put_file(
        self,
        name: str,
        path: str,
        branch: str,
        content: str,
        current_sha: str | None,
    ) -> None: ...

    def open_pull_request(
        self,
        name: str,
        branch: str,
        base: str,
    ) -> dict[str, Any] | None: ...

    def create_pull_request(
        self,
        name: str,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]: ...

    def update_pull_request(
        self,
        name: str,
        number: int,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]: ...


class GitHubAPI:
    """Small REST client for GitHub App or user tokens."""

    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        if not token:
            raise ValueError("GH_TOKEN is required")
        self._token = token
        self._api_url = api_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_not_found: bool = False,
    ) -> Any:
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"{self._api_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "mobilint-code-review-sync",
                "X-GitHub-Api-Version": API_VERSION,
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
        except HTTPError as error:
            if allow_not_found and error.code == 404:
                return None
            detail = error.read(2048).decode("utf-8", errors="replace")
            raise SyncError(f"GitHub API {method} {path} failed ({error.code}): {detail}") from error
        except URLError as error:
            raise SyncError(f"GitHub API {method} {path} failed: {error.reason}") from error
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SyncError(f"GitHub API {method} {path} returned invalid JSON") from error

    @staticmethod
    def _repo_path(name: str) -> str:
        validate_repository_name(name)
        return f"/repos/{name}"

    def repository(self, name: str) -> dict[str, Any]:
        return self._request("GET", self._repo_path(name))

    def actions_enabled(self, name: str) -> bool:
        result = self._request("GET", f"{self._repo_path(name)}/actions/permissions")
        return bool(result.get("enabled", False))

    def branch_sha(self, name: str, branch: str) -> str | None:
        validate_branch_name(branch)
        result = self._request(
            "GET",
            f"{self._repo_path(name)}/git/ref/heads/{quote(branch, safe='/')}",
            allow_not_found=True,
        )
        if result is None:
            return None
        return str(result["object"]["sha"])

    def create_branch(self, name: str, branch: str, sha: str) -> None:
        validate_branch_name(branch)
        self._request(
            "POST",
            f"{self._repo_path(name)}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
        )

    def file_content(self, name: str, path: str, branch: str) -> tuple[str, str] | None:
        validate_branch_name(branch)
        result = self._request(
            "GET",
            f"{self._repo_path(name)}/contents/{quote(path, safe='/')}?"
            f"{urlencode({'ref': branch})}",
            allow_not_found=True,
        )
        if result is None:
            return None
        if (
            not isinstance(result, dict)
            or result.get("type") != "file"
            or result.get("encoding") != "base64"
        ):
            raise SyncError(f"{name}:{path} is not a regular base64-encoded file")
        try:
            encoded = "".join(str(result["content"]).split())
            content = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError) as error:
            raise SyncError(f"{name}:{path} has invalid content data") from error
        return content, str(result["sha"])

    def put_file(
        self,
        name: str,
        path: str,
        branch: str,
        content: str,
        current_sha: str | None,
    ) -> None:
        validate_branch_name(branch)
        payload: dict[str, Any] = {
            "message": COMMIT_MESSAGE,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if current_sha:
            payload["sha"] = current_sha
        self._request(
            "PUT",
            f"{self._repo_path(name)}/contents/{quote(path, safe='/')}",
            payload,
        )

    def open_pull_request(
        self,
        name: str,
        branch: str,
        base: str,
    ) -> dict[str, Any] | None:
        validate_branch_name(branch)
        validate_branch_name(base)
        query = urlencode(
            {
                "state": "open",
                "head": f"mobilint:{branch}",
                "base": base,
                "per_page": 10,
            }
        )
        pulls = self._request("GET", f"{self._repo_path(name)}/pulls?{query}")
        return pulls[0] if pulls else None

    def create_pull_request(
        self,
        name: str,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"{self._repo_path(name)}/pulls",
            {"head": branch, "base": base, "title": title, "body": body},
        )

    def update_pull_request(
        self,
        name: str,
        number: int,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"{self._repo_path(name)}/pulls/{number}",
            {"base": base, "title": title, "body": body},
        )


def validate_repository_name(name: str) -> None:
    """Reject repositories outside the intended organization or unsafe paths."""
    if not isinstance(name, str) or not REPOSITORY_RE.fullmatch(name):
        raise ValueError(f"invalid managed repository name: {name!r}")


def validate_branch_name(branch: str) -> None:
    """Apply a conservative Git branch allowlist before API path construction."""
    if (
        not isinstance(branch, str)
        or not BRANCH_RE.fullmatch(branch)
        or branch.endswith(".lock")
    ):
        raise ValueError(f"invalid branch name: {branch!r}")


def load_manifest(path: Path) -> list[RepositoryConfig]:
    """Load and strictly validate the JSON manifest."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("version") != 1
        or not isinstance(document.get("repositories"), list)
    ):
        raise ValueError("manifest must contain version 1 and a repositories list")
    repositories: list[RepositoryConfig] = []
    seen: set[str] = set()
    for raw in document["repositories"]:
        if not isinstance(raw, dict):
            raise ValueError("each manifest repository must be an object")
        name = raw.get("name")
        validate_repository_name(name)
        if name in seen:
            raise ValueError(f"duplicate manifest repository: {name}")
        seen.add(name)
        enabled = raw.get("enabled")
        adopt_existing = raw.get("adopt_existing")
        if not isinstance(enabled, bool) or not isinstance(adopt_existing, bool):
            raise ValueError(f"{name}: enabled and adopt_existing must be booleans")
        profile = raw.get("profile", "default")
        overrides = raw.get("overrides", {})
        if not isinstance(profile, str) or not isinstance(overrides, dict):
            raise ValueError(f"{name}: profile must be a string and overrides must be an object")
        repositories.append(
            RepositoryConfig(name, enabled, adopt_existing, profile, overrides)
        )
    return repositories


def select_repositories(
    repositories: list[RepositoryConfig],
    selected: str | None,
) -> list[RepositoryConfig]:
    """Select one enrolled repository without broadening manifest scope."""
    if not selected:
        return repositories
    validate_repository_name(selected)
    matches = [
        repository
        for repository in repositories
        if repository.name == selected
    ]
    if not matches:
        raise ValueError(f"repository is not enrolled: {selected}")
    return matches


def github_app_repository_scope(
    repositories: list[RepositoryConfig],
) -> str:
    """Return the enabled repository slugs accepted by the token action."""
    enabled = [
        repository.name.removeprefix("mobilint/")
        for repository in repositories
        if repository.enabled
    ]
    if not enabled:
        raise ValueError("selection contains no enabled managed repositories")
    return ",".join(enabled)


def classify(content: str | None, canonical: str) -> str:
    """Classify the caller on a repository's default branch."""
    if content is None:
        return "missing"
    if content == canonical:
        return "synchronized"
    if content.startswith(MANAGED_PREFIX):
        return "managed_outdated"
    return "unmanaged"


def pull_request_body() -> str:
    """Return stable PR text so existing automation PRs can be updated."""
    return "\n".join(
        [
            "## Summary",
            "",
            "- replace the repository-local Codex review workflow with the centrally managed caller",
            "- inherit policy limits and review behavior from `mobilint/.github`",
            "- subscribe to `pull_request.synchronize` while leaving the central "
            "`review_on_pr_synchronize` policy disabled by default",
            "",
            "This branch is managed by `mobilint/.github` and will be updated "
            "idempotently when the canonical caller changes.",
            "",
            "## Rollback",
            "",
            "Close this PR before merge, or revert the caller commit after merge and "
            "disable the repository in the central manifest.",
        ]
    )


def sync_repository(
    service: RepositoryService,
    config: RepositoryConfig,
    canonical: str,
    *,
    dry_run: bool,
) -> SyncResult:
    """Plan or apply synchronization for one repository."""
    if not config.enabled:
        return SyncResult(config.name, "disabled", message="manifest entry is disabled")

    metadata = service.repository(config.name)
    default_branch = str(metadata.get("default_branch", ""))
    validate_branch_name(default_branch)
    if metadata.get("archived") is True:
        return SyncResult(
            config.name,
            "skipped_archived",
            default_branch=default_branch,
            message="repository is archived",
        )
    if not service.actions_enabled(config.name):
        return SyncResult(
            config.name,
            "skipped_actions_disabled",
            default_branch=default_branch,
            message="GitHub Actions is disabled",
        )

    default_file = service.file_content(config.name, CALLER_PATH, default_branch)
    default_content = default_file[0] if default_file else None
    classification = classify(default_content, canonical)
    if classification == "synchronized":
        return SyncResult(
            config.name,
            "synchronized",
            default_branch=default_branch,
            classification=classification,
            message="default branch already matches the canonical caller",
        )
    if classification == "unmanaged" and not config.adopt_existing:
        return SyncResult(
            config.name,
            "blocked_unmanaged",
            default_branch=default_branch,
            classification=classification,
            message="existing caller is unmanaged and adoption is not permitted",
        )

    if dry_run:
        return SyncResult(
            config.name,
            "would_sync",
            default_branch=default_branch,
            classification=classification,
            changed=True,
            message=f"would synchronize {classification} caller through a pull request",
        )

    branch_sha = service.branch_sha(config.name, AUTOMATION_BRANCH)
    if branch_sha is None:
        default_sha = service.branch_sha(config.name, default_branch)
        if default_sha is None:
            raise SyncError(f"{config.name}: default branch ref is missing")
        service.create_branch(config.name, AUTOMATION_BRANCH, default_sha)

    branch_file = service.file_content(config.name, CALLER_PATH, AUTOMATION_BRANCH)
    branch_content = branch_file[0] if branch_file else None
    branch_file_sha = branch_file[1] if branch_file else None
    changed = branch_content != canonical
    if changed:
        service.put_file(
            config.name,
            CALLER_PATH,
            AUTOMATION_BRANCH,
            canonical,
            branch_file_sha,
        )

    body = pull_request_body()
    pull = service.open_pull_request(
        config.name,
        AUTOMATION_BRANCH,
        default_branch,
    )
    if pull is None:
        pull = service.create_pull_request(
            config.name,
            AUTOMATION_BRANCH,
            default_branch,
            PR_TITLE,
            body,
        )
        status = "pull_request_created"
    else:
        pull_base = pull.get("base", {})
        metadata_current = (
            pull.get("title") == PR_TITLE
            and pull.get("body") == body
            and isinstance(pull_base, dict)
            and pull_base.get("ref") == default_branch
        )
        if metadata_current:
            status = "pull_request_updated" if changed else "pull_request_current"
        else:
            pull = service.update_pull_request(
                config.name,
                int(pull["number"]),
                default_branch,
                PR_TITLE,
                body,
            )
            status = "pull_request_updated"

    return SyncResult(
        config.name,
        status,
        default_branch=default_branch,
        classification=classification,
        changed=changed,
        pull_request_url=str(pull.get("html_url", "")),
        message="canonical caller is ready on the automation pull request",
    )


def synchronize(
    service: RepositoryService,
    repositories: list[RepositoryConfig],
    canonical: str,
    *,
    dry_run: bool,
) -> list[SyncResult]:
    """Synchronize repositories independently so one API failure cannot corrupt others."""
    results: list[SyncResult] = []
    for config in repositories:
        try:
            results.append(sync_repository(service, config, canonical, dry_run=dry_run))
        except (SyncError, ValueError, KeyError, TypeError) as error:
            results.append(
                SyncResult(config.name, "error", message=str(error))
            )
    return results


def human_summary(results: list[SyncResult]) -> str:
    """Render a concise deterministic Markdown summary."""
    lines = ["## Codex review caller synchronization", ""]
    for result in results:
        detail = result.message
        if result.pull_request_url:
            detail = f"{detail} ({result.pull_request_url})"
        lines.append(f"- `{result.repository}`: **{result.status}** — {detail}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/code-review-repositories.json"),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("workflow-templates/code-review.yml"),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--repository", help="select one owner/repository entry")
    parser.add_argument(
        "--print-app-repositories",
        action="store_true",
        help="print enabled repository slugs for actions/create-github-app-token",
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repositories = load_manifest(args.manifest)
        repositories = select_repositories(repositories, args.repository)
        if args.print_app_repositories:
            print(github_app_repository_scope(repositories))
            return 0
        canonical = args.template.read_text(encoding="utf-8")
        service = GitHubAPI(os.environ.get("GH_TOKEN", ""))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    results = synchronize(
        service,
        repositories,
        canonical,
        dry_run=args.dry_run or args.check,
    )
    document = {
        "version": 1,
        "mode": "check" if args.check else "dry-run" if args.dry_run else "apply",
        "results": [asdict(result) for result in results],
    }
    encoded = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    summary = human_summary(results)
    print(encoded, end="")
    print(summary, file=sys.stderr, end="")
    if args.json_output:
        args.json_output.write_text(encoded, encoding="utf-8")
    if args.summary_output:
        args.summary_output.write_text(summary, encoding="utf-8")

    failures = {"error", "blocked_unmanaged"}
    if any(result.status in failures for result in results):
        return 1
    if args.check and any(
        result.status
        not in {
            "synchronized",
            "disabled",
            "skipped_archived",
            "skipped_actions_disabled",
        }
        for result in results
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
