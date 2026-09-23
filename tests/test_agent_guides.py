from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/check-agent-guides.yml"


class AgentGuideLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self.secret = Path(self.temporary.name) / "private"
        self.secret.write_text("PRIVATE_SENTINEL_NEVER_PRINTED")
        self.script = textwrap.dedent(WORKFLOW.read_text().split("        run: |\n", 1)[1])
        self.git("init", "-q")
        for source in [ROOT / "AGENTS.md", *(ROOT / ".agents/skills").rglob("*")]:
            if source.is_file():
                target = self.repo / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
        (self.repo / ".claude").mkdir()
        (self.repo / "CLAUDE.md").symlink_to("AGENTS.md")
        (self.repo / ".claude/skills").symlink_to("../.agents/skills")
        self.git("add", ".")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                       capture_output=True, text=True)

    def check(self, succeeds: bool) -> None:
        result = subprocess.run(["bash", "-c", self.script], cwd=self.repo,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, succeeds, result.stdout + result.stderr)
        self.assertNotIn("PRIVATE_SENTINEL_NEVER_PRINTED", result.stdout + result.stderr)
        self.assertEqual(self.secret.read_text(), "PRIVATE_SENTINEL_NEVER_PRINTED")

    def test_exact_relative_links_pass(self) -> None:
        self.check(True)

    def test_arbitrary_guide_targets_fail_without_dereferencing(self) -> None:
        for target in (str(self.secret), "../private", "AGENTS.md\n", "missing"):
            with self.subTest(target=target):
                path = self.repo / "CLAUDE.md"
                path.unlink()
                path.symlink_to(target)
                self.git("add", "CLAUDE.md")
                self.check(False)

    def test_external_skill_directory_link_is_rejected(self) -> None:
        path = self.repo / ".claude/skills"
        path.unlink()
        path.symlink_to(str(self.secret.parent))
        self.git("add", ".claude/skills")
        self.check(False)

    def test_copied_guide_is_rejected(self) -> None:
        path = self.repo / "CLAUDE.md"
        path.unlink()
        path.write_bytes((self.repo / "AGENTS.md").read_bytes())
        self.git("add", "CLAUDE.md")
        self.check(False)

    def test_canonical_sources_must_remain_regular_files(self) -> None:
        sources = [self.repo / "AGENTS.md", *(self.repo / ".agents/skills").rglob("SKILL.md")]
        for path in sources:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.unlink()
                path.symlink_to(str(self.secret))
                self.git("add", str(path.relative_to(self.repo)))
                self.check(False)
                path.unlink()
                path.write_bytes(original)
                self.git("add", str(path.relative_to(self.repo)))


if __name__ == "__main__":
    unittest.main()
