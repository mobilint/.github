from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import unittest

from scripts import sync_code_review_callers as sync


CANONICAL = (
    "# managed-by: mobilint/.github\n"
    "# managed-template: code-review\n"
    "# managed-template-version: 1\n"
)


@dataclass
class RepoState:
    default_branch: str = "main"
    archived: bool = False
    actions: bool = True
    branches: dict[str, str] = field(default_factory=dict)
    files: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    pull: dict | None = None

    def __post_init__(self) -> None:
        self.branches.setdefault(self.default_branch, f"{self.default_branch}-sha")
        self.files.setdefault(self.default_branch, {})


class FakeService:
    def __init__(self, states: dict[str, RepoState]) -> None:
        self.states = states
        self.calls: list[tuple] = []

    def repository(self, name: str) -> dict:
        self.calls.append(("repository", name))
        state = self.states[name]
        return {
            "default_branch": state.default_branch,
            "archived": state.archived,
        }

    def actions_enabled(self, name: str) -> bool:
        self.calls.append(("actions_enabled", name))
        return self.states[name].actions

    def branch_sha(self, name: str, branch: str) -> str | None:
        self.calls.append(("branch_sha", name, branch))
        return self.states[name].branches.get(branch)

    def create_branch(self, name: str, branch: str, sha: str) -> None:
        self.calls.append(("create_branch", name, branch, sha))
        state = self.states[name]
        source = next(key for key, value in state.branches.items() if value == sha)
        state.branches[branch] = f"{branch}-sha"
        state.files[branch] = dict(state.files[source])

    def file_content(
        self, name: str, path: str, branch: str
    ) -> tuple[str, str] | None:
        self.calls.append(("file_content", name, path, branch))
        return self.states[name].files.get(branch, {}).get(path)

    def put_file(
        self,
        name: str,
        path: str,
        branch: str,
        content: str,
        current_sha: str | None,
    ) -> None:
        self.calls.append(("put_file", name, path, branch, current_sha))
        self.states[name].files.setdefault(branch, {})[path] = (
            content,
            "managed-file-sha",
        )

    def open_pull_request(
        self, name: str, branch: str, base: str
    ) -> dict | None:
        self.calls.append(("open_pull_request", name, branch, base))
        return self.states[name].pull

    def create_pull_request(
        self,
        name: str,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> dict:
        self.calls.append(("create_pull_request", name, branch, base))
        pull = {
            "number": 7,
            "html_url": f"https://github.com/{name}/pull/7",
            "title": title,
            "body": body,
            "base": {"ref": base},
        }
        self.states[name].pull = pull
        return pull

    def update_pull_request(
        self,
        name: str,
        number: int,
        base: str,
        title: str,
        body: str,
    ) -> dict:
        self.calls.append(("update_pull_request", name, number, base))
        pull = {
            "number": number,
            "html_url": f"https://github.com/{name}/pull/{number}",
            "title": title,
            "body": body,
            "base": {"ref": base},
        }
        self.states[name].pull = pull
        return pull


def config(
    name: str = "mobilint/example",
    *,
    enabled: bool = True,
    adopt: bool = False,
) -> sync.RepositoryConfig:
    return sync.RepositoryConfig(name, enabled, adopt, "default", {})


class SynchronizerTests(unittest.TestCase):
    def test_missing_target_dry_run(self) -> None:
        service = FakeService({"mobilint/example": RepoState()})
        result = sync.sync_repository(service, config(), CANONICAL, dry_run=True)
        self.assertEqual(result.status, "would_sync")
        self.assertEqual(result.classification, "missing")
        self.assertFalse(any(call[0] == "put_file" for call in service.calls))

    def test_already_synchronized_target(self) -> None:
        state = RepoState()
        state.files["main"][sync.CALLER_PATH] = (CANONICAL, "file-sha")
        result = sync.sync_repository(
            FakeService({"mobilint/example": state}),
            config(),
            CANONICAL,
            dry_run=False,
        )
        self.assertEqual(result.status, "synchronized")
        self.assertFalse(result.changed)

    def test_managed_outdated_target(self) -> None:
        state = RepoState()
        state.files["main"][sync.CALLER_PATH] = (
            sync.MANAGED_PREFIX + "# managed-template-version: 0\n",
            "old-sha",
        )
        result = sync.sync_repository(
            FakeService({"mobilint/example": state}),
            config(),
            CANONICAL,
            dry_run=True,
        )
        self.assertEqual(result.classification, "managed_outdated")
        self.assertEqual(result.status, "would_sync")

    def test_unmanaged_target_without_adoption(self) -> None:
        state = RepoState()
        state.files["main"][sync.CALLER_PATH] = ("name: local\n", "local-sha")
        service = FakeService({"mobilint/example": state})
        result = sync.sync_repository(
            service, config(adopt=False), CANONICAL, dry_run=False
        )
        self.assertEqual(result.status, "blocked_unmanaged")
        self.assertFalse(any(call[0] == "create_branch" for call in service.calls))

    def test_unmanaged_target_with_adoption(self) -> None:
        state = RepoState()
        state.files["main"][sync.CALLER_PATH] = ("name: local\n", "local-sha")
        result = sync.sync_repository(
            FakeService({"mobilint/example": state}),
            config(adopt=True),
            CANONICAL,
            dry_run=False,
        )
        self.assertEqual(result.status, "pull_request_created")
        self.assertEqual(result.classification, "unmanaged")

    def test_legacy_explicit_policy_caller_is_adoption_drift(self) -> None:
        state = RepoState(default_branch="master")
        state.files["master"][sync.CALLER_PATH] = (
            """
name: Codex Review
jobs:
  codex-review:
    uses: mobilint/.github/.github/workflows/codex-pr-review.yml@main
    with:
      max_files: 200
      max_diff_chars: 200000
      max_concurrent_mention_reviews: 5
""",
            "legacy-sha",
        )
        result = sync.sync_repository(
            FakeService({"mobilint/example": state}),
            config(adopt=True),
            CANONICAL,
            dry_run=True,
        )
        self.assertEqual(result.default_branch, "master")
        self.assertEqual(result.classification, "unmanaged")
        self.assertEqual(result.status, "would_sync")

    def test_discovers_main_and_master_default_branches(self) -> None:
        for default_branch in ("main", "master"):
            with self.subTest(default_branch=default_branch):
                state = RepoState(default_branch=default_branch)
                result = sync.sync_repository(
                    FakeService({"mobilint/example": state}),
                    config(),
                    CANONICAL,
                    dry_run=True,
                )
                self.assertEqual(result.default_branch, default_branch)

    def test_existing_branch_and_pull_request_are_updated(self) -> None:
        state = RepoState()
        state.branches[sync.AUTOMATION_BRANCH] = "automation-sha"
        state.files[sync.AUTOMATION_BRANCH] = {
            sync.CALLER_PATH: (sync.MANAGED_PREFIX + "old\n", "old-sha")
        }
        state.pull = {
            "number": 9,
            "html_url": "https://github.com/mobilint/example/pull/9",
            "title": "old",
            "body": "old",
            "base": {"ref": "main"},
        }
        service = FakeService({"mobilint/example": state})
        result = sync.sync_repository(
            service, config(), CANONICAL, dry_run=False
        )
        self.assertEqual(result.status, "pull_request_updated")
        self.assertTrue(any(call[0] == "put_file" for call in service.calls))
        self.assertTrue(
            any(call[0] == "update_pull_request" for call in service.calls)
        )
        self.assertFalse(
            any(call[0] == "create_pull_request" for call in service.calls)
        )

    def test_second_apply_is_idempotent(self) -> None:
        state = RepoState()
        service = FakeService({"mobilint/example": state})
        first = sync.sync_repository(
            service, config(), CANONICAL, dry_run=False
        )
        first_call_count = len(service.calls)
        second = sync.sync_repository(
            service, config(), CANONICAL, dry_run=False
        )
        second_calls = service.calls[first_call_count:]
        self.assertEqual(first.status, "pull_request_created")
        self.assertEqual(second.status, "pull_request_current")
        self.assertFalse(second.changed)
        self.assertFalse(any(call[0] == "put_file" for call in second_calls))
        self.assertFalse(
            any(call[0] == "create_pull_request" for call in second_calls)
        )
        self.assertFalse(
            any(call[0] == "update_pull_request" for call in second_calls)
        )

    def test_archived_and_actions_disabled_repositories_are_skipped(self) -> None:
        archived = sync.sync_repository(
            FakeService({"mobilint/example": RepoState(archived=True)}),
            config(),
            CANONICAL,
            dry_run=False,
        )
        disabled = sync.sync_repository(
            FakeService({"mobilint/example": RepoState(actions=False)}),
            config(),
            CANONICAL,
            dry_run=False,
        )
        self.assertEqual(archived.status, "skipped_archived")
        self.assertEqual(disabled.status, "skipped_actions_disabled")

    def test_api_error_does_not_stop_other_repositories(self) -> None:
        class PartialFailureService(FakeService):
            def repository(self, name: str) -> dict:
                if name == "mobilint/broken":
                    raise sync.SyncError("simulated API failure")
                return super().repository(name)

        service = PartialFailureService(
            {
                "mobilint/broken": RepoState(),
                "mobilint/healthy": RepoState(),
            }
        )
        results = sync.synchronize(
            service,
            [config("mobilint/broken"), config("mobilint/healthy")],
            CANONICAL,
            dry_run=True,
        )
        self.assertEqual([result.status for result in results], ["error", "would_sync"])

    def test_manifest_supports_disabled_adoption_and_future_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(
                """
                {
                  "version": 1,
                  "repositories": [{
                    "name": "mobilint/example",
                    "enabled": false,
                    "adopt_existing": true,
                    "profile": "large",
                    "overrides": {"future": 1}
                  }]
                }
                """,
                encoding="utf-8",
            )
            entry = sync.load_manifest(path)[0]
        self.assertFalse(entry.enabled)
        self.assertTrue(entry.adopt_existing)
        self.assertEqual(entry.profile, "large")
        self.assertEqual(entry.overrides, {"future": 1})

    def test_unsafe_names_are_rejected(self) -> None:
        for repository in ("other/example", "mobilint/a/b", "mobilint/../x"):
            with self.subTest(repository=repository):
                with self.assertRaises(ValueError):
                    sync.validate_repository_name(repository)
        for branch in ("../main", "main..x", "refs//heads", "bad@{ref"):
            with self.subTest(branch=branch):
                with self.assertRaises(ValueError):
                    sync.validate_branch_name(branch)


if __name__ == "__main__":
    unittest.main()
