# Repository Agent Guide

## Purpose

Maintain Mobilint's shared GitHub configuration, reusable Codex review workflow,
canonical caller example, organization profile, and clone badge automation.

`AGENTS.md` and `CLAUDE.md` are byte-for-byte mirrors. The repository skill is
also mirrored under `.agents/skills` and `.claude/skills`. Update both copies in
the same change and run the synchronization workflow before finishing.

## Repository Map

- `.github/workflows/codex-pr-review.yml`: reusable workflow that resolves
  events, enforces trust gates, manages reactions, and invokes the self-hosted
  review action.
- `.github/workflows/code-review.yml`: canonical caller example copied into
  Mobilint repositories; it must be byte-identical to the workflow template.
- `workflow-templates/code-review.yml`: single canonical managed caller source
  and official organization workflow template.
- `workflow-templates/code-review.properties.json`: organization template
  metadata.
- `.github/workflows/sync-code-review-callers.yml`: GitHub App authenticated
  scheduled/manual caller distributor.
- `.github/workflows/check-code-review-sync.yml`: caller, contract, YAML, and
  synchronization test workflow.
- `config/code-review-repositories.json`: explicit managed-repository manifest.
- `config/codex-review-action-contract.json`: expected public action input
  contract.
- `scripts/sync_code_review_callers.py`: idempotent pull-request synchronizer.
- `tests/`: offline caller, contract, API-failure, and idempotency tests.
- `.github/workflows/update-clone-badge.yml`: clone badge publisher that writes
  generated data to the orphan `badges` branch.
- `.github/workflows/check-agent-guides.yml`: CI guard that requires the Codex
  and Claude guide and skill copies to remain byte-identical.
- `README.md`: repository landing page and clone badge.
- `profile/README.md`: Mobilint organization profile.
- `assets/`: organization profile assets.
- `.agents/skills/maintain-review-automation/`: Codex maintenance skill.
- `.claude/skills/maintain-review-automation/`: Claude maintenance skill.

## Cross-Repository Contract

The reusable workflow calls `mobilint/codex-review-action@main`. When changing
an action input, reaction lifecycle, event mode, prompt behavior, finding
format, sandbox policy, or delivery behavior:

1. Inspect `../codex-review-action/action.yml`.
2. Update the action implementation and tests when its contract changes.
3. Update `codex-pr-review.yml`, the canonical workflow template, its exact
   example copy, the contract fixture, and relevant READMEs.
4. Update both agent guides and both skill copies when their instructions or
   repository map are affected.
5. Validate both repositories before committing.

Do not assume a change in only one repository completes the feature.

## Review Behavior Invariants

- Use visible `P0`, `P1`, and `P2` priorities for findings.
- Add a temporary 👀 reaction when a review starts and remove that exact
  reaction before publishing the final result.
- For a clean review, add 👍 and do not post a success comment.
- Keep failure and error notices visible.
- Ignore `@mobilint-review` inside blockquotes, fenced code, indented code, and
  inline code.
- Require trusted authors for automatic reviews and trusted commenters for
  mention reviews.
- Keep automatic reviews bounded and keep mention review payloads within the
  documented safety limit.
- Keep the shared capacity defaults synchronized: 500 changed files, 1,000,000
  diff characters, and 10 concurrent mention-review slots per PR.
- Keep consumer callers policy-free: events, minimal permissions, and the
  central reusable-workflow reference only.
- Subscribe managed callers to `synchronize`, while keeping
  `review_on_pr_synchronize: false` centrally unless policy deliberately
  changes.

## Security Invariants

- Keep permissions minimal: `actions: read`, `contents: read`, and write access
  only for pull requests and issues.
- Keep `review_on_member_pr_only: true` unless an explicit security review
  approves a broader caller.
- Keep `allow_unsafe_no_sandbox_fallback: false` in the canonical caller.
- Fail closed when the Codex sandbox cannot start. Never enable
  `--dangerously-bypass-approvals-and-sandbox` through a shared example.
- Run trust checks before dispatching work to the self-hosted runner.
- Treat event bodies, PR metadata, diffs, branch names, and repository contents
  as untrusted input.
- Validate numeric GitHub identifiers before interpolating them into API paths.
- Keep mention parsing linear-time and avoid backtracking regular expressions
  over attacker-controlled comments.
- In pull-request checks, never dereference or print repository paths before
  proving they are regular tracked files. Compare trusted Git index metadata or
  blob IDs, and disable checkout credential persistence when it is unnecessary.

## Workflow Editing Rules

- Preserve `workflow_call` input defaults unless a deliberate contract
  migration updates all callers.
- Pass untrusted or externally derived values through `env` rather than
  interpolating GitHub expressions directly into shell code.
- Use quoted shell expansions and `set -euo pipefail`.
- Use `submitted` for `pull_request_review`; use `created` for
  `pull_request_review_comment` and `issue_comment`.
- Use current action majors that run on the supported GitHub Actions Node.js
  runtime; use `actions/checkout@v6`.
- Keep the canonical caller conservative because it is copied to other
  repositories.
- Do not commit generated clone badge JSON to `main`; keep it on `badges`.
- Never edit `.github/workflows/code-review.yml` independently. Edit
  `workflow-templates/code-review.yml` and keep the example byte-identical.
- Synchronize consumers only through deterministic branches and pull requests;
  never push their default branches.
- Use the dedicated least-privilege GitHub App for cross-repository writes.

## Documentation Maintenance

Before finishing any repository change, check whether it changes:

- file layout or ownership;
- workflow triggers, permissions, inputs, outputs, defaults, or runner labels;
- reviewer UX, reaction behavior, finding limits, or mention handling;
- sandbox, trust, token, or API-path security boundaries;
- validation commands or deployment procedures.

If so, update `AGENTS.md`, `CLAUDE.md`, and both copies of the maintenance
skill in the same commit. Keep each mirrored pair byte-identical. Do not update
only the Codex or only the Claude copy.

## Validation

Run at minimum:

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/codex-pr-review.yml', encoding='utf-8')); yaml.safe_load(open('.github/workflows/code-review.yml', encoding='utf-8')); yaml.safe_load(open('.github/workflows/check-agent-guides.yml', encoding='utf-8')); print('workflow YAML OK')"
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
cmp workflow-templates/code-review.yml .github/workflows/code-review.yml
cmp AGENTS.md CLAUDE.md
cmp .agents/skills/maintain-review-automation/SKILL.md .claude/skills/maintain-review-automation/SKILL.md
cmp .agents/skills/maintain-review-automation/agents/openai.yaml .claude/skills/maintain-review-automation/agents/openai.yaml
git diff --check
```

When the action contract changes, also run the `codex-review-action` tests.

## Git Hygiene

- Preserve unrelated user changes.
- Keep commits focused.
- Do not push generated badge content to `main`.
- Do not bypass validation hooks or weaken a security control to make a check
  pass.
