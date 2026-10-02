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
    def run_gate(self, comments=None, reviews=None, reactions=None, wait='0', mode='auto', later=None, api_error=False):
        section = WORKFLOW.read_text().split('      - name: Decide fallback execution\n', 1)[1]
        script = textwrap.dedent(section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = {'comments': comments or [], 'reviews': reviews or [], 'reactions': reactions or []}
            (root / 'fixture.json').write_text(json.dumps(fixture))
            (root / 'later.json').write_text(json.dumps(later or fixture))
            (root / 'api_error').write_text('yes' if api_error else 'no')
            gh = root / 'gh'
            gh.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
p = pathlib.Path('.')
assert sys.argv[1:3] == ['api', 'graphql']
query = sys.argv[sys.argv.index('-f') + 1]
assert all(field + '(last:100)' in query for field in ['reviews', 'comments', 'reactions'])
with (p / 'calls').open('a') as log:
    log.write('graphql\\n')
fixture = json.loads((p / 'fixture.json').read_text())
for review in fixture['reviews']:
    review['commit'] = {'oid': review.pop('commit_id', None)}
for item in fixture['reviews'] + fixture['comments']:
    user = item.get('user') or {}
    if user.get('login', '').endswith('[bot]'):
        user['login'] = user['login'][:-5]
        user['__typename'] = 'Bot'
    else:
        user['__typename'] = 'User'
    item['user'] = user
for reaction in fixture['reactions']:
    reaction['content'] = {'eyes': 'EYES', '+1': 'THUMBS_UP'}.get(reaction['content'], reaction['content'])
response = {'data': {'repository': {'pullRequest': {key: {'nodes': value} for key, value in fixture.items()}}}}
if (p / 'api_error').read_text() == 'yes':
    response['errors'] = [{'message': 'partial failure'}]
print(json.dumps(response))
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
            # Advance Bash's elapsed clock without real sleeps.
            script = ('test_elapsed=0\nsleep() { command sleep "$1"; test_elapsed=$((test_elapsed + $1)); }\n'
                      + script.replace('SECONDS', 'test_elapsed'))
            subprocess.run(['bash', '-c', script], cwd=root, env=env, check=True,
                           capture_output=True, text=True, timeout=30)
            sleeps = (root / 'sleeps').read_text().splitlines() if (root / 'sleeps').exists() else []
            self.calls = len((root / 'calls').read_text().splitlines()) if (root / 'calls').exists() else 0
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
        out, sleeps = self.run_gate(reviews=[review], wait='5')
        self.assertIn('run_local=false', out)
        self.assertEqual(sleeps, [])
        self.assertEqual(self.calls, 1)

    def test_thumbsup_ends_positive_wait(self):
        reaction = {'user': {'login': BOT}, 'content': '+1', 'created_at': TIME}
        out, sleeps = self.run_gate(reactions=[reaction], wait='5')
        self.assertIn('run_local=false', out)
        self.assertEqual(sleeps, [])
        self.assertEqual(self.calls, 1)

    def test_default_wait_query_budget(self):
        out, sleeps = self.run_gate(wait='5')
        self.assertIn('reason=no-official-review', out)
        self.assertEqual(sum(map(int, sleeps)), 300)
        self.assertLessEqual(self.calls, 21)

    def test_wait_bounds_leave_gate_headroom(self):
        for wait, seconds in [('20', 1200), ('21', 300), ('60', 300),
                              ('bogus', 300), ('-1', 300), ('00', 0)]:
            with self.subTest(wait=wait):
                out, sleeps = self.run_gate(wait=wait)
                self.assertIn('reason=no-official-review', out)
                self.assertEqual(sum(map(int, sleeps)), seconds)
                self.assertLessEqual(self.calls, seconds // 15 + 1)

    def test_partial_graphql_error_fails_visibly(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_gate(api_error=True)

    def test_mentions_bypass_wait(self):
        out, sleeps = self.run_gate(mode='mention', wait='5')
        self.assertIn('reason=mention', out)
        self.assertEqual(sleeps, [])

    def test_event_time_comes_from_trigger_snapshot(self):
        text = WORKFLOW.read_text()
        self.assertIn('.pull_request.updated_at // .pull_request.created_at', text)
        self.assertNotIn("'.updatedAt // \"\"' <<<", text)
