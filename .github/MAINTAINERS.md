# GitHub automation operations

This guide is for maintainers of Mobilint's centralized GitHub workflows. The
repository root README remains a user-facing overview.

## Architecture and trust boundary

```text
consumer .github/workflows/code-review.yml
  -> mobilint/.github/.github/workflows/codex-pr-review.yml@main
  -> mobilint/codex-review-action@2454440c864b485d23ae3c3a4078f0adb445c497
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
The hosted cleanup job removes the temporary eyes reaction when the self-hosted
review fails or is canceled before its action can perform cleanup.

When event association metadata is inconclusive, the permission fallback trusts
only an explicit `write`, `maintain`, or `admin` effective repository permission;
API success by itself and `read` or `none` permissions remain untrusted.

## Canonical managed caller

`workflow-templates/code-review.yml` is the only hand-edited source. It is also
the official organization workflow template. The backward-compatible example
at `.github/workflows/code-review.yml` must remain byte-identical.

`.github/workflows/sync-code-review-template.yml` copies the canonical file to
the example automatically. It runs on GitHub-hosted `ubuntu-latest` for
same-repository pull requests that change the canonical file, after canonical
changes reach `main`, and on manual dispatch from `main`. Fork pull requests are
skipped because their branches must not receive a write token; their authors
must include the exact-copy example in the PR. The job executes no repository
code, validates the canonical path as a tracked regular file, constructs the
copy from the Git blob, and pushes without force. Its scoped `GITHUB_TOKEN` may
write repository contents only; it uses neither the Codex runner nor a GitHub
App credential.

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
while repositories migrate. `allow_unsafe_no_sandbox_fallback` is deprecated
and ignored, including when a legacy caller passes `true`. Sandbox mode and unsafe
fallback behavior are not caller-configurable: the reusable workflow hard-codes
a read-only sandbox and fails closed when it cannot start. No Actions-variable
override layer is enabled yet; repository-specific `CODEX_REVIEW_*` variables
are reserved for a future, strictly parsed profile system. Security-sensitive
trust, permissions, runner, ownership, and sandbox settings remain central.

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
already-current branch produces no commit or metadata update. Before applying
trusted PR metadata, the synchronizer requires the automation branch to descend
from the current default branch and to change exactly the managed caller path.
A comparison 404, including unrelated history, also fails this check; other
API errors abort visibly. It resets a branch that fails that check and verifies the complete diff again
after writing the caller.

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

The automatic template-copy workflow affects only the two files inside this
central repository. It does not distribute updates to consumer repositories;
consumer audit and migration remain explicit operator-run tasks.

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

The reusable workflow pins the review action to an immutable, reviewed commit.
The central reusable workflow itself remains on `@main`; neither central
repository currently has a validated `stable` branch. The release sequence is:

1. Merge reviewed action changes on `main` and record the exact candidate SHA.
   Keep the production reusable workflow's action pin unchanged during testing.
   Record the currently deployed central commit, action SHA, and consumer channel
   (`main` or `stable`) so the previous validated release is identifiable.
2. In a controlled repository, use a dedicated trusted canary workflow that
   invokes `mobilint/codex-review-action@<candidate-SHA>` directly, with explicit
   `auto` and `mention` inputs and their corresponding event contexts. Do not
   route this canary through the production reusable workflow, which still
   references the old action. Verify checkout, sandbox, and review delivery.
3. Through a reviewed PR, advance the reusable workflow's action pin on `main`
   to exactly the SHA exercised by the direct-action canary and synchronize its
   contract fixture. Record the resulting central workflow commit and validate
   its automatic and mention routing in the controlled repository.
4. Only after that validation, create or advance `mobilint/.github`'s protected
   `stable` branch to the recorded central workflow commit. Create or advance
   the action repository's protected `stable` branch to the tested action
   revision as well; the reusable workflow continues to use the immutable SHA.
   Follow the authorized branch-protection/release process for these updates.
5. Verify that the distributed `mobilint/.github` `stable` ref resolves to the
   validated central commit, and exercise automatic and mention routing through
   `codex-pr-review.yml@stable` in the controlled repository. If either check
   fails, do not distribute the caller; correct the release and repeat validation.
6. Change the canonical caller to reference that validated `@stable` workflow,
   keep the generated example identical, and copy the caller or explicitly run
   the local synchronizer. For later releases, repeat the candidate canary,
   reviewed pin promotion, stable-ref advancement, and stable-routing validation.

Organization administrators must create branch protection for both `stable`
branches, require the repositories' CI checks and reviews, restrict direct
pushes, and document who advances the refs. Repository code cannot apply those
settings by itself.

## Rollback

- Before merge, close any manually created consumer synchronization PR.
- After merge, revert the managed caller commit in the consumer and set its
  manifest entry to `enabled: false` before the next sync.
- For central policy or action rollback, use a reviewed revert/fix PR on `main`
  to restore a validated known-good workflow and immutable action SHA, updating
  the matching contract fixture. Preserve unrelated security fixes. Test both
  automatic and mention behavior in the controlled repository and record the
  resulting rollback commit; `@main` consumers receive it without caller changes.
- For consumers on `@stable`, reverting `main` alone is insufficient. Through
  the authorized protected-branch release process, advance `mobilint/.github`'s
  `stable` branch to that validated rollback commit. Prefer a forward revert/fix
  commit so rollback does not require a force-push. Verify the deployed stable
  ref and its action pin, then recheck automatic and mention routing through
  `codex-pr-review.yml@stable` before declaring recovery. Stop further caller
  distribution if validation fails; repeat the correction and channel checks.
  Consumers already using `@stable` need no caller edit. Updating the action
  repository's `stable` branch alone cannot roll back the immutable action SHA
  embedded in the central workflow.
- To roll back a caller schema, revert the canonical template, synchronize its
  generated example, and update affected consumer callers through reviewed PRs.
  Verify the workflow ref those callers actually use; template changes alone do
  not update existing consumers.

Comment/review events that require default-branch workflows will not run until
the managed caller has merged into the consumer's default branch.

The pinned action infers omitted `mode` from `event_name`. The central workflow
already resolves `auto` and `mention` at its gate and forwards that explicit
mode; callers need no new input. The shared action fixture has no `mode` default.

Caller reads traverse non-recursive Git trees and read verified regular blobs,
without following symlinks. Branch reuse requires both the expected diff and
the canonical caller blob identity. Even when the default caller is current,
check/dry-run reports an untrusted existing branch as drift; apply resets it
to the default branch and verifies it before reporting synchronization. A
regular already-current branch remains idempotent and produces no write.

## Shared Codex and Claude guidance

Edit `AGENTS.md` and `.agents/skills` as the canonical sources. `CLAUDE.md`
links to `AGENTS.md`; `.claude/skills` links to `../.agents/skills`. Changes through
either path affect the same files. Check out with Git symlink support enabled
(`core.symlinks=true`) so these entries materialize as links rather than text.
The guide CI checks canonical files as tracked `100644` blobs and accepts only
those two exact `120000` link targets by Git blob identity. It never dereferences
PR-controlled links. Other source-file and managed-caller checks still reject
symlinks. The regression tests cover valid links and hostile alternatives.
