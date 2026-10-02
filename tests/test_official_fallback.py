"""Run the workflow's actual fallback shell against a fake GitHub API."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/codex-pr-review.yml'
BOT = 'chatgpt-codex-connector[bot]'
LIMIT = 'You have reached your Codex usage limits for code reviews.'
TIME = '2026-10-02T02:59:00Z'


@unittest.skipUnless(shutil.which('jq'), 'jq is required for workflow shell tests')
class OfficialFallbackTests(unittest.TestCase):
    def run_gate(self, comments=None, reviews=None, reactions=None, wait='0', mode='auto', later=None):
        section = WORKFLOW.read_text().split('      - name: Decide fallback execution\n', 1)[1]
        script = textwrap.dedent(section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = {'comments': comments or [], 'reviews': reviews or [], 'reactions': reactions or []}
            (root / 'fixture.json').write_text(json.dumps(fixture))
            (root / 'later.json').write_text(json.dumps(later or fixture))
            gh = root / 'gh'
            gh.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
p = pathlib.Path('.')
endpoint = sys.argv[2].split('?')[0].rsplit('/', 1)[-1]
print(json.dumps(json.loads((p / 'fixture.json').read_text())[endpoint]))
''')
            gh.chmod(0o755)
            sleep = root / 'sleep'
            sleep.write_text('''#!/bin/sh
printf '%s\\n' "$1" >> sleeps
cp later.json fixture.json
''')
            sleep.chmod(0o755)
            output = root / 'output'
            env = dict(os.environ, PATH=str(root)+os.pathsep+os.environ['PATH'],
                       GITHUB_OUTPUT=str(output), WAIT_MINUTES=wait, TRIGGER_MODE=mode,
                       REPO='mobilint/example', PR_NUMBER='26', PR_HEAD_SHA='current', PR_EVENT_TIME=TIME)
            subprocess.run(['bash', '-c', script], cwd=root, env=env, check=True,
                           capture_output=True, text=True, timeout=5)
            sleeps = (root / 'sleeps').read_text().splitlines() if (root / 'sleeps').exists() else []
            return output.read_text(), sleeps

    def comment(self, body=LIMIT, login=BOT, time=TIME):
        return {'user': {'login': login}, 'body': body, 'created_at': time}

    def test_current_and_legacy_quota_errors_skip_wait(self):
        for body in [LIMIT, 'Codex usage limits have been reached for code reviews.',
                     'Credits must be used to enable repository wide code reviews.']:
            with self.subTest(body=body):
                out, sleeps = self.run_gate(comments=[self.comment(body)], wait='05')
                self.assertIn('reason=official-usage-limit', out)
                self.assertEqual(sleeps, [])

    def test_error_arriving_during_wait_overrides_eyes(self):
        eyes = {'user': {'login': BOT}, 'content': 'eyes', 'created_at': TIME}
        out, sleeps = self.run_gate(reactions=[eyes], wait='5', later={
            'comments': [self.comment()], 'reviews': [], 'reactions': [eyes]})
        self.assertIn('reason=official-usage-limit', out)
        self.assertEqual(sleeps, ['15'])

    def test_spoofed_and_old_comments_do_not_trigger_quota_fallback(self):
        out, _ = self.run_gate(comments=[self.comment(login='attacker'),
                                       self.comment(time='2026-10-01T00:00:00Z')])
        self.assertIn('reason=no-official-review', out)

    def test_review_requires_current_head(self):
        review = {'user': {'login': BOT}, 'body': LIMIT, 'submitted_at': TIME, 'commit_id': 'old'}
        out, _ = self.run_gate(reviews=[review])
        self.assertIn('reason=no-official-review', out)
        review['commit_id'] = 'current'
        out, sleeps = self.run_gate(reviews=[review], wait='5')
        self.assertIn('reason=official-usage-limit', out)
        self.assertEqual(sleeps, [])

    def test_success_signal_still_suppresses_fallback(self):
        review = {'user': {'login': BOT}, 'body': 'Looks good', 'submitted_at': TIME, 'commit_id': 'current'}
        out, _ = self.run_gate(reviews=[review])
        self.assertIn('run_local=false', out)

    def test_mentions_bypass_wait(self):
        out, sleeps = self.run_gate(mode='mention', wait='5')
        self.assertIn('reason=mention', out)
        self.assertEqual(sleeps, [])

    def test_event_time_comes_from_trigger_snapshot(self):
        text = WORKFLOW.read_text()
        self.assertIn('.pull_request.updated_at // .pull_request.created_at', text)
        self.assertNotIn("'.updatedAt // \"\"' <<<", text)
