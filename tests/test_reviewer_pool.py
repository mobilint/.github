from pathlib import Path
import json
import os
import subprocess
import tempfile
import textwrap
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
                    self.assertEqual(args[-(len(extra) - 1):], extra[1:])
            result = subprocess.run(['bash', str(ROOT / 'scripts/runner-codex'), 'sandbox', 'sh', '-lc', 'true'],
                                    env={**os.environ, 'CODEX_REAL_BIN': str(fake)},
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), ['sandbox', 'sh', '-lc', 'true'])

    def test_prompt_data_cannot_disable_config_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'real-codex'
            fake.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            fake.chmod(0o755)
            for prompt_args in (['Review code containing --ignore-user-config as text'],
                                ['--', '--ignore-user-config'],
                                ['--ignore-user-config', '--', '--ignore-user-config']):
                result = subprocess.run(['bash', str(ROOT / 'scripts/runner-codex'), 'exec', *prompt_args],
                                        env={**os.environ, 'CODEX_REAL_BIN': str(fake)},
                                        capture_output=True, text=True, check=True)
                args = json.loads(result.stdout)
                self.assertEqual(args[:2], ['exec', '--ignore-user-config'])
                if '--' in prompt_args:
                    marker = args.index('--')
                    self.assertEqual(args[:marker].count('--ignore-user-config'), 1)
                    self.assertEqual(args[marker + 1:], ['--ignore-user-config'])
                else:
                    self.assertEqual(args[-1], prompt_args[0])

    def test_pool_probe_keeps_allocation_guards_and_optional_authentication(self) -> None:
        text = (ROOT / '.github/workflows/check-reviewer-pool.yml').read_text()
        self.assertEqual(text.count("github.repository == 'mobilint/.github'"), 2)
        self.assertEqual(text.count("github.event.repository.default_branch"), 2)
        for fragment in ('max-parallel: ${{ fromJSON(needs.prepare.outputs.parallelism) }}',
                         'parallelism: ${{ steps.matrix.outputs.parallelism }}', 'type: number', 'needs: prepare',
                         'slot: ${{ fromJSON(needs.prepare.outputs.slots) }}',
                         'if: inputs.authenticated_smoke', '--model gpt-6-luna',
                         'model_reasoning_effort="max"', '--sandbox read-only'):
            self.assertIn(fragment, text)

    def test_real_matrix_planner_accepts_flexible_counts_and_rejects_bad_inputs(self) -> None:
        text = (ROOT / '.github/workflows/check-reviewer-pool.yml').read_text()
        # Execute the real workflow's hosted planner, rather than a duplicate validator.
        run_block = text.split('        run: |\n', 1)[1].split('\n  probe:', 1)[0]
        script = textwrap.dedent(run_block)
        for value in ('1', '2', '5', '8', '256', '0', '-1', '257', '1.5', 'nan',
                      '', '1; echo injected', '$(id)', '9' * 10000):
            with self.subTest(value=value[:30]), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'output'
                result = subprocess.run(['bash', '-c', script],
                                        env={**os.environ, 'PARALLELISM': value,
                                             'GITHUB_OUTPUT': str(output)},
                                        capture_output=True, text=True)
                if value in ('1', '2', '5', '8', '256'):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    values = dict(line.split('=', 1) for line in output.read_text().splitlines())
                    self.assertEqual(int(values['parallelism']), int(value))
                    self.assertEqual(json.loads(values['slots']), list(range(1, int(value) + 1)))
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(output.read_text(), '')
                    self.assertIn('positive whole number', result.stderr)
