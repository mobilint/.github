from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "workflow-templates" / "code-review.yml"
EXAMPLE = ROOT / ".github" / "workflows" / "code-review.yml"
REUSABLE = ROOT / ".github" / "workflows" / "codex-pr-review.yml"
APP_SYNCHRONIZER = ROOT / ".github" / "workflows" / "sync-code-review-callers.yml"


class ManagedCallerTests(unittest.TestCase):
    def test_root_readme_remains_the_landing_page_with_clone_badge(self) -> None:
        self.assertFalse((ROOT / ".github" / "README.md").exists())
        self.assertTrue((ROOT / ".github" / "MAINTAINERS.md").is_file())
        self.assertIn(
            "[![GitHub clones]",
            (ROOT / "README.md").read_text(encoding="utf-8"),
        )

    def test_canonical_and_example_are_identical(self) -> None:
        self.assertEqual(CANONICAL.read_bytes(), EXAMPLE.read_bytes())

    def test_template_metadata_is_valid_json(self) -> None:
        metadata = json.loads(
            (ROOT / "workflow-templates" / "code-review.properties.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(metadata["name"], "Mobilint Codex PR Review")
        self.assertTrue(metadata["description"])

    def test_required_events_and_actions_are_present(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        required = (
            "pull_request:",
            "- opened",
            "- reopened",
            "- ready_for_review",
            "- synchronize",
            "issue_comment:",
            "pull_request_review:",
            "- submitted",
            "pull_request_review_comment:",
            "- created",
        )
        for fragment in required:
            self.assertIn(fragment, text)
        self.assertNotIn("pull_request_target", text)

    def test_permissions_are_minimal_and_policy_is_not_duplicated(self) -> None:
        text = CANONICAL.read_text(encoding="utf-8")
        self.assertIn("actions: read", text)
        self.assertIn("contents: read", text)
        self.assertIn("pull-requests: write", text)
        self.assertIn("issues: write", text)
        self.assertNotIn("actions: write", text)
        self.assertNotIn("\n    with:", text)
        self.assertNotIn("secrets: inherit", text)
        self.assertIn(
            "uses: mobilint/.github/.github/workflows/codex-pr-review.yml@main",
            text,
        )

    def test_reusable_defaults_remain_central(self) -> None:
        text = REUSABLE.read_text(encoding="utf-8")
        for name, expected in (
            ("max_files", "500"),
            ("max_diff_chars", "1000000"),
            ("review_on_pr_synchronize", "false"),
            ("max_concurrent_mention_reviews", "10"),
        ):
            pattern = (
                rf"(?ms)^      {re.escape(name)}:\n"
                rf".*?^        default: {re.escape(expected)}$"
            )
            self.assertRegex(text, pattern)

    def test_reusable_action_call_matches_contract_fixture(self) -> None:
        contract = json.loads(
            (ROOT / "config" / "codex-review-action-contract.json").read_text(
                encoding="utf-8"
            )
        )
        text = REUSABLE.read_text(encoding="utf-8")
        run_review = text[text.index("  run-review:") : text.index("  post-failure:")]
        with_block = run_review[run_review.index("        with:") :]
        passed = {
            match.group(1)
            for match in re.finditer(r"^          ([a-z0-9_]+):", with_block, re.M)
        }
        self.assertEqual(passed, set(contract["action_inputs"]))

    def test_reusable_workflow_preserves_review_boundaries(self) -> None:
        text = REUSABLE.read_text(encoding="utf-8")
        for fragment in (
            "OWNER|MEMBER|COLLABORATOR",
            "chatgpt-codex-connector[bot]",
            "-f content='eyes'",
            "group: codex",
            "labels: codex-reviewer",
            "sandbox_mode: read-only",
            "allow_unsafe_no_sandbox_fallback:",
            "needs.gate.outputs.run_local == 'true'",
            "Codex review did not complete successfully.",
        ):
            self.assertIn(fragment, text)
        self.assertNotIn("pull_request_target", text)

    def test_unattended_app_synchronizer_is_not_installed(self) -> None:
        self.assertFalse(APP_SYNCHRONIZER.exists())


if __name__ == "__main__":
    unittest.main()
