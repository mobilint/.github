from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReviewerPoolTests(unittest.TestCase):
    def test_wrapper_defaults_and_explicit_action_arguments_coexist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'real-codex'
            fake.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            fake.chmod(0o755)
            for extra in ([], ['--ignore-user-config', '--model', 'gpt-6.1-sol',
                               '-c', 'model_reasoning_effort="high"']):
                result = subprocess.run(['bash', str(ROOT / 'scripts/runner-codex'), 'exec', *extra],
                                        env={**os.environ, 'CODEX_REAL_BIN': str(fake)},
                                        capture_output=True, text=True, check=True)
                args = json.loads(result.stdout)
                self.assertEqual(args.count('--ignore-user-config'), 1)
                self.assertIn('model="gpt-6-luna"', args)
                self.assertIn('model_reasoning_effort="max"', args)
                if extra:
                    self.assertEqual(args[-len(extra):], extra)
            result = subprocess.run(['bash', str(ROOT / 'scripts/runner-codex'), 'sandbox', 'sh', '-lc', 'true'],
                                    env={**os.environ, 'CODEX_REAL_BIN': str(fake)},
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), ['sandbox', 'sh', '-lc', 'true'])

    def test_pool_probe_keeps_allocation_guards_and_optional_authentication(self) -> None:
        text = (ROOT / '.github/workflows/check-reviewer-pool.yml').read_text()
        self.assertEqual(text.count("github.repository == 'mobilint/.github'"), 2)
        self.assertEqual(text.count("github.event.repository.default_branch"), 2)
        for fragment in ('max-parallel: 5', "options: ['1', '2', '3', '4', '5']",
                         '1|2|3|4|5)', 'needs: prepare',
                         'slot: ${{ fromJSON(needs.prepare.outputs.slots) }}',
                         'if: inputs.authenticated_smoke', '--model gpt-6-luna',
                         'model_reasoning_effort="max"', '--sandbox read-only'):
            self.assertIn(fragment, text)
