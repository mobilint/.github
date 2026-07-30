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
reach the self-hosted runner. The synchronization workflow never checks out
consumer repositories or executes their code.

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

## Synchronization operation

`scripts/sync_code_review_callers.py` discovers each repository's default
branch through the GitHub API, classifies the caller, and creates or updates the
deterministic `automation/sync-codex-review` branch and one pull request. It
never writes the default branch. Existing automation PRs are reused, and an
already-current branch produces no commit or metadata update.

The command prints JSON to stdout and a Markdown summary to stderr:

```bash
GH_TOKEN=... python3 scripts/sync_code_review_callers.py \
  --dry-run \
  --repository mobilint/mblt-model-zoo
```

Use `--check` for a read-only audit that exits nonzero on drift. Omit both
`--dry-run` and `--check` to apply. `--json-output` and `--summary-output` write
the two report formats to files.

`.github/workflows/sync-code-review-callers.yml` applies changes after relevant
central files merge to `main`, audits once daily at 02:43 UTC, and supports a
manual dry run or one-repository selection. Workflow concurrency prevents
racing sync runs. Archived repositories and repositories with Actions disabled
are reported and skipped; an API failure is isolated to its repository.

## GitHub App setup

Create a GitHub App dedicated to caller synchronization and install it only on
the repositories listed in the manifest. Configure:

- repository variable `CODE_REVIEW_SYNC_APP_CLIENT_ID`;
- Actions secret `CODE_REVIEW_SYNC_APP_PRIVATE_KEY`.

Grant only these repository permissions:

- Actions: read, to detect repositories where Actions is disabled;
- Contents: write, to read content and create/update the automation branch;
- Pull requests: write, to create and update migration PRs;
- Workflows: write, which GitHub requires for changes under
  `.github/workflows`.

Metadata read is implicit for GitHub Apps. Do not use a personal access token as
the scheduled workflow credential, and do not install the App on repositories
that are not managed.

See GitHub's documentation for
[choosing App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)
and the maintained
[`actions/create-github-app-token`](https://github.com/actions/create-github-app-token)
action. GitHub explicitly requires the Workflows repository permission to edit
files under `.github/workflows`.

## Validation

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
python3 -c "import yaml; [yaml.safe_load(open(path, encoding='utf-8')) for path in ['.github/workflows/code-review.yml', '.github/workflows/codex-pr-review.yml', '.github/workflows/sync-code-review-callers.yml', 'workflow-templates/code-review.yml']]"
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
6. Let synchronization distribute that caller change through PRs.

Organization administrators must create branch protection for both `stable`
branches, require the repositories' CI checks and reviews, restrict direct
pushes, and document who advances the refs. Repository code cannot apply those
settings by itself.

## Rollback

- Before merge, close the consumer synchronization PR.
- After merge, revert the managed caller commit in the consumer and set its
  manifest entry to `enabled: false` before the next sync.
- To roll back central policy, revert the reusable workflow commit; consumers
  using `@main` receive the rollback without caller changes.
- To roll back a caller schema, revert the canonical template and let the
  synchronizer open or update consumer PRs.

Comment/review events that require default-branch workflows will not run until
the managed caller has merged into the consumer's default branch.
