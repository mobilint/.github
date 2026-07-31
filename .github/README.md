# GitHub automation operations

This guide is for maintainers of Mobilint's centralized GitHub workflows. The
repository root README remains a user-facing overview.

## Architecture and trust boundary

```text
consumer .github/workflows/code-review.yml
  -> mobilint/.github/.github/workflows/codex-pr-review.yml@main
  -> mobilint/codex-review-action@main
  -> self-hosted runner group codex, label codex-reviewer
```

The consumer file contains events and minimum token permissions only. Trust
checks, official-Codex fallback detection, reactions, limits, sandbox policy,
and runner selection remain in the reusable workflow. The caller subscribes to
`pull_request.synchronize`, but central
`review_on_pr_synchronize: false` remains authoritative, so pushed commits do
not start automatic reviews unless central policy changes or a legacy caller
explicitly opts in.

The gate runs on GitHub-hosted infrastructure before untrusted PR content can
reach the self-hosted runner. Caller distribution is an operator-run maintenance
task; no GitHub App or scheduled cross-repository writer is used.

## Canonical managed caller

`workflow-templates/code-review.yml` is the only hand-edited source. It is also
the official organization workflow template. The backward-compatible example
at `.github/workflows/code-review.yml` must remain byte-identical; CI rejects
drift.

The template metadata is
`workflow-templates/code-review.properties.json`. Managed callers contain
versioned marker comments so the synchronizer can distinguish managed files
from repository-owned workflows.

## Central policy and overrides

Normal callers pass no `with:` values. Current central defaults include:

- 500 changed files before summary-only mode;
- 1,000,000 diff characters before truncation;
- 10 concurrent mention-review slots per PR;
- 5 minutes to wait for an official Codex review;
- automatic review on `synchronize` disabled;
- read-only sandbox with unsafe fallback disabled.

The existing `workflow_call` inputs remain supported for backward compatibility
while repositories migrate. No Actions-variable override layer is enabled yet;
repository-specific `CODEX_REVIEW_*` variables are reserved for a future,
strictly parsed profile system. Security-sensitive trust, permissions, runner,
ownership, and sandbox settings remain central.

## Enrolling and disabling repositories

Edit `config/code-review-repositories.json`.

```json
{
  "name": "mobilint/example",
  "enabled": true,
  "adopt_existing": false,
  "profile": "default",
  "overrides": {}
}
```

- Add repositories explicitly; the tool never enumerates and enrolls the
  organization.
- Set `adopt_existing: true` once when an existing unmanaged caller should be
  replaced. Without it, synchronization refuses to overwrite the file.
- Set `enabled: false` to stop audits and updates without deleting history.
- Remove the entry after outstanding automation PRs are closed if the
  repository should no longer be managed.
- `profile` and `overrides` are reserved metadata. They do not currently change
  synchronization or review policy.

The manifest contains an explicit snapshot of all 21 Mobilint repositories as
of 2026-07-30. Seventeen active repositories are enabled. Four archived
repositories remain listed with `enabled: false`, so they are visible in policy
without entering routine audits. New organization repositories must still be
added deliberately.

## Manual audit and synchronization

`scripts/sync_code_review_callers.py` discovers each repository's default
branch through the GitHub API, classifies the caller, and creates or updates the
deterministic `automation/sync-codex-review` branch and one pull request. It
never writes the default branch. Existing automation PRs are reused, and an
already-current branch produces no commit or metadata update.

Run it from a trusted administrator workstation or the existing maintenance
server using an explicitly authenticated `gh` session. It is not invoked by
GitHub Actions. The command prints JSON to stdout and a Markdown summary to
stderr:

```bash
GH_TOKEN="$(gh auth token)" python3 scripts/sync_code_review_callers.py \
  --dry-run \
  --repository mobilint/mblt-model-zoo
```

Use `--check` for a read-only audit that exits nonzero on drift. Omit both
`--dry-run` and `--check` to apply, and do that only after reviewing the
selected repository and current authentication scope. `--json-output` and
`--summary-output` write the two report formats to files. Archived repositories
and repositories with Actions disabled are reported and skipped; an API failure
is isolated to its repository.

Normal caller updates may also be copied manually. Do not configure
`CODE_REVIEW_SYNC_APP_CLIENT_ID` or `CODE_REVIEW_SYNC_APP_PRIVATE_KEY`; this
repository deliberately has no unattended App-based synchronizer.

## Validation

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
python3 -c "import yaml; [yaml.safe_load(open(path, encoding='utf-8')) for path in ['.github/workflows/code-review.yml', '.github/workflows/codex-pr-review.yml', 'workflow-templates/code-review.yml']]"
cmp workflow-templates/code-review.yml .github/workflows/code-review.yml
git diff --check
```

Unit tests use an in-memory GitHub service and make no live writes. Use an
explicit `--dry-run` for live API validation.

## Release channel

Production references remain on `@main`; neither central repository currently
has a validated `stable` branch. The release sequence is:

1. Merge compatible `.github` and action changes on `main`.
2. Canary automatic and mention behavior on a controlled repository.
3. Create and protect `stable` branches in both central repositories.
4. Change the reusable workflow to call the action at `@stable`.
5. Change the canonical caller to call the reusable workflow at `@stable`.
6. Copy the updated caller manually or run the local synchronizer explicitly.

Organization administrators must create branch protection for both `stable`
branches, require the repositories' CI checks and reviews, restrict direct
pushes, and document who advances the refs. Repository code cannot apply those
settings by itself.

## Rollback

- Before merge, close any manually created consumer synchronization PR.
- After merge, revert the managed caller commit in the consumer and set its
  manifest entry to `enabled: false` before the next sync.
- To roll back central policy, revert the reusable workflow commit; consumers
  using `@main` receive the rollback without caller changes.
- To roll back a caller schema, revert the canonical template and manually
  update affected consumer callers.

Comment/review events that require default-branch workflows will not run until
the managed caller has merged into the consumer's default branch.
