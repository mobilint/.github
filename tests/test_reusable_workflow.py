import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "codex-pr-review.yml"


class ReusableWorkflowSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_text = WORKFLOW.read_text(encoding="utf-8")

    def test_trust_fallback_uses_positive_collaborator_check(self) -> None:
        """A successful permission lookup is not proof of collaboration."""
        trust_step = self.workflow_text.split(
            "      - name: Check trusted association\n", 1
        )[1].split("\n      - name:", 1)[0]

        self.assertIn(
            'gh api "/repos/${REPO}/collaborators/${PR_AUTHOR}"', trust_step
        )
        self.assertIn(
            'gh api "/repos/${REPO}/collaborators/${COMMENTER}"', trust_step
        )
        self.assertNotIn("/permission", trust_step)


if __name__ == "__main__":
    unittest.main()
