---
name: maintain-review-automation
description: Maintain Mobilint's centralized GitHub Codex review workflows and canonical caller example. Use when changing workflow triggers, permissions, trust gates, reactions, reusable inputs or outputs, sandbox policy, mention handling, finding limits, clone badge automation, or the contract with mobilint/codex-review-action.
---

# Maintain Review Automation

## Establish Scope

1. Read the root agent guide (`AGENTS.md` or `CLAUDE.md`) completely.
2. Inspect the caller, reusable workflow, and affected action contract before
   editing.
3. Preserve unrelated worktree changes.
4. Treat `.github/workflows/code-review.yml` as the conservative template that
   other Mobilint repositories will copy.

## Trace Cross-Repository Behavior

For reviewer behavior changes, trace this path:

```text
repository event
  -> code-review.yml
  -> codex-pr-review.yml gate and acknowledgement
  -> mobilint/codex-review-action inputs
  -> final reaction, review, or error notice
```

Inspect `../codex-review-action/action.yml`, `scripts/run-review.sh`, prompt
templates, formatter, and tests whenever the shared contract is affected.

## Preserve Invariants

- Keep caller permissions minimal.
- Keep trusted-author and trusted-commenter gates ahead of self-hosted work.
- Keep `allow_unsafe_no_sandbox_fallback: false`; fail closed on sandbox
  startup failure.
- Use temporary 👀 acknowledgement, reaction-only 👍 for clean reviews, and
  visible error notices.
- Ignore quoted and code-formatted mentions with linear-time parsing.
- Validate GitHub identifiers before API path interpolation.
- Keep finding and payload limits explicit.
- Use `submitted` for pull request reviews and `created` for individual review
  comments and issue comments.
- Keep clone badge output on the orphan `badges` branch.
- Use `actions/checkout@v6`.
- For pull-request checks, reject non-`100644` index entries and compare Git
  blob IDs without dereferencing or printing PR-controlled working-tree paths.
- Set `persist-credentials: false` on read-only checkouts that do not need to
  perform authenticated Git operations.

## Update Documentation

After changing repository behavior, layout, contracts, defaults, security
boundaries, or validation:

1. Update `README.md` when user-facing behavior changed.
2. Update both `AGENTS.md` and `CLAUDE.md`.
3. Update this skill and
   `.claude/skills/maintain-review-automation/SKILL.md`.
4. Keep each mirrored pair byte-identical.
5. Update both `agents/openai.yaml` copies if the skill purpose or default
   prompt changed.

Never update only the Codex or only the Claude documentation.

## Validate

Run:

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/codex-pr-review.yml', encoding='utf-8')); yaml.safe_load(open('.github/workflows/code-review.yml', encoding='utf-8')); yaml.safe_load(open('.github/workflows/check-agent-guides.yml', encoding='utf-8')); print('workflow YAML OK')"
cmp AGENTS.md CLAUDE.md
cmp .agents/skills/maintain-review-automation/SKILL.md .claude/skills/maintain-review-automation/SKILL.md
cmp .agents/skills/maintain-review-automation/agents/openai.yaml .claude/skills/maintain-review-automation/agents/openai.yaml
git diff --check
```

Run the `codex-review-action` unit and shell checks when changing the
cross-repository action contract. Inspect the final diff for secure defaults
and copied-example safety before committing.
