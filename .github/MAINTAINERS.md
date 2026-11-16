# GitHub automation operations

This guide is for maintainers of Mobilint's centralized GitHub workflows. The
repository root README remains a user-facing overview.

## Architecture and trust boundary

```text
consumer .github/workflows/code-review.yml
  -> mobilint/.github/.github/workflows/codex-pr-review.yml@28642ba1d8df2f8ff63f19113b06186191527d8f
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
The canonical caller pins the central workflow to a reviewed full commit SHA
from `mobilint/.github`. Verify the workflow exists at that exact repository/ref;
a syntactically valid SHA from another repository cannot be used. Existing
consumers on mutable refs remain on those refs until their migration PRs merge.

1. Merge reviewed action changes and record the exact candidate SHA. Keep the
   production action pin unchanged during testing. Record each consumer's
   deployed workflow SHA/ref and its action pin for rollback.
2. In a controlled repository, invoke the candidate action SHA directly with
   explicit auto and mention inputs and corresponding event contexts. Verify
   checkout, sandbox, and review delivery; the production workflow still uses
   the old action during this canary.
3. Through a reviewed PR, promote exactly the tested action SHA in the central
   reusable workflow and synchronize its contract fixture. Record the resulting
   central commit and validate automatic and mention routing at that exact SHA.
4. Update the canonical caller to that validated central SHA and keep its
   generated example identical. Distribute through reviewed consumer PRs using
   the operator-run synchronizer. Confirm each consumer's deployed pin after merge.

A protected `stable` branch may track release bookkeeping, but distributed
callers and the review action must keep immutable SHA references. Advancing a
branch does not update those consumers. Runner-group workflow restrictions must
permit the selected workflow SHA before migration; administrators manage that
setting outside this repository.

## Rollback

- Before merge, close any manually created consumer synchronization PR.
- After merge, revert the managed caller commit in the consumer and set its
  manifest entry to `enabled: false` before the next sync.
- For central policy or action rollback, use a reviewed revert/fix PR to restore
  a validated workflow and immutable action SHA, keeping unrelated security fixes.
  Validate automatic and mention behavior, then update the canonical caller and
  affected consumers to that rollback commit through reviewed PRs. Reverting
  `main` or advancing `stable` alone cannot update SHA-pinned consumers.
- Audit legacy consumers still on mutable refs and validate every deployed
  channel during rollback. Do not declare recovery until the actual consumer
  refs resolve to the validated rollback workflow and action.
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

## Multiple review runners

Register each runner under a distinct name in group `codex`, with custom label
`codex-reviewer`. Use separate installation and `_work` directories (on this
server: `~/actions-runner` and `~/actions-runner-2`) and keep both services online.
Each service user needs the tools listed in the action README, Codex credentials,
and a working read-only sandbox. Shared-host runners share machine capacity;
adding services does not add CPU or memory. The deployed action at `2454440`
already creates a unique directory with `mktemp -d` under `TMPDIR` or `/tmp`
and cleans up only its own directory. The candidate in codex-review-action PR #12
adds preference for `RUNNER_TEMP`; that behavior is not deployed until its
approval, direct-action canary, and a separate reviewed central pin update.
No custom dispatcher or runner-name binding is needed.

An organization administrator should verify both registrations are online with
the matching label, and that group `codex` permits each consuming repository
(and its reusable workflow if workflow restrictions are enabled). Listing these
settings through the REST API requires organization runner administration access;
ordinary repository access is insufficient.

After the central workflow is merged to the default branch, manually dispatch
`Check reviewer runner pool` in `mobilint/.github` on the default branch. A job
guard skips other repositories and refs before runner allocation; workflow
concurrency serializes probe batches so repeated dispatches cannot run extra
batches alongside the active probe. Organization runner-group access restrictions
remain the administrator-controlled trust boundary for workflow execution.
It runs two independent jobs
with `max-parallel: 2`, no checkout and no write permissions. Each checks tools and
sandbox startup and stays occupied for 20 seconds. When both runners are idle,
verify distinct runner names and overlapping execution intervals in the two job
logs. A serial run alone does not prove failure: a runner may have been busy or
offline. This smoke check does not authenticate a model request or publish a review.

GitHub schedules eligible jobs, not jobs still waiting at the hosted gate or
blocked by concurrency. Automatic reviews remain latest-update-wins per PR;
mention reviews retain their bounded per-PR slots with `cancel-in-progress: false`,
so a newer mention never interrupts the running review. A colliding mention waits
for that slot even if another runner is idle. GitHub permits only one pending job
per group by default: a third colliding request replaces the older pending job,
not the running job, even with `cancel-in-progress: false`. See the official
[concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
These are intentional review policies, not runner affinity. An already-running review is not migrated. A queued
eligible job with an idle matching runner warrants checking its labels, group
access, online status and runner service logs before changing concurrency policy.

## Official connector quota fallback

The central reusable workflow checks official output immediately, then every
15 seconds during the configured wait (five minutes by default). A recognized
quota or review-credit error from `chatgpt-codex-connector[bot]` starts local
fallback on the next check, including “You have reached your Codex usage limits
for code reviews.” Completed reviews or 👍 end the wait immediately. Silence retains the timeout;
mention reviews bypass it.
Checks use the triggering PR event timestamp, require the current head for
reviews, and ignore matching text from other authors or older comments. An eyes
reaction does not end polling early because the connector can report quota
failure afterward. Trust gates and runner scheduling still apply.

This behavior is implemented in the central workflow, not the action. Consumers
pinned to older workflow SHAs need a reviewed caller-pin update after this
central change merges; their behavior does not change merely by updating the
action. Keep timeout, author, timestamp, and head guards covered by regression
tests when editing fallback detection. Polling uses one bounded GraphQL query
per check for the newest 100 reviews, comments, and reactions. Partial API errors
fail visibly. Configured waits accept 0–20 minutes; invalid or larger values use
the five-minute default, leaving headroom within the 30-minute gate timeout.

The managed-caller regression test also locks the exact reviewed central SHA.
Update that assertion alongside a pin promotion only after verifying the new
repository/ref and workflow path; do not derive its expected value from the caller.

## Model configuration and rollout status

The candidate action accepts `model` and `reasoning_effort`, defaulting to
`gpt-6-luna` and `max`. Both sandbox execution paths use validated CLI arguments
and `--ignore-user-config`; no connectors or interactive profiles are inherited
from the user config. Project configuration remains subject to Codex's normal
trust and configuration handling. Model names are limited to 128 ASCII letters,
digits, dots, underscores, and hyphens, starting with a letter or digit. Effort
is low/medium/high/xhigh/max. Invalid inputs fall back to the defaults.

The managed caller now proposes central revision
`4cabbe49c0e7a521c24c36459b572910386cb40d`, verified through the GitHub Contents
API and merged PR #14. It includes prompt quota fallback, but still uses the
previous action pin. It does not deploy this candidate action.

The previous action pin `2454440c864b485d23ae3c3a4078f0adb445c497`
and action main `64ec9f23019340099d0f045e6fc02963fae07ea8` have divergent
history. The three commits exclusive to the previous pin are mode inference
and merge commits. Main retains mode inference with regression coverage; the
candidate adds explicit model selection. Review the complete comparison rather
than assuming a fast-forward release. Before merging the central promotion,
merge/review the action candidate, run its exact SHA directly for auto and
mention events, record canary run links, and update the central pin if the
merge changes that SHA. Then validate central routing and distribute the
resulting central SHA through operator-run consumer PRs. Do not point consumer
callers at an unvalidated central candidate.

## Runner installation and removal

Use one dedicated installation and `_work` directory per runner under
`~/codex-runners/`. The current pool is `codex-reviewer-1` through
`codex-reviewer-5`, group `codex` (ID 3), label `codex-reviewer`. Five eligible
jobs can execute concurrently, subject to the trust gate, per-PR concurrency,
shared host resources, and account quota. GitHub chooses any idle matching
runner. Production reviews must never select runner names individually.

Prerequisites: Linux x64, systemd, `gh`, `git`, `jq`, `python3`, `bubblewrap`, and
a Codex CLI supporting `exec --ignore-user-config` (tested with 0.169.0).
Authenticate Codex as the service user with `codex login`; `codex login status`
shows local login state. An authenticated smoke request verifies the actual
model access. The GitHub CLI operator needs organization runner administration
permission; OAuth tokens need `admin:org`. Keep credentials out of the repo.
Never run registration/removal commands under `set -x`.

Run from a trusted checkout of this repository as the service user. Install the
versioned wrapper once; it preserves the Luna/max defaults for older deployed
actions and lets newer actions override them through explicit CLI settings:

```bash
runner_root="$HOME/codex-runners"
mkdir -p "$runner_root/bin" "$runner_root/downloads"
# Verify this points to the real CLI, not the wrapper itself.
"$HOME/.local/bin/codex" --version
install -m 755 scripts/runner-codex "$runner_root/bin/codex"
```

The wrapper expects the actual CLI at `~/.local/bin/codex`. If it is installed
elsewhere, set `CODEX_REAL_BIN` in each installation's `.env` to its absolute
path. Never point that setting back to the wrapper. Services run as this user
and share its Codex authentication. Interactive Codex configuration is unchanged.

Download and verify a runner release (or reuse an already verified archive):

```bash
release=$(gh api repos/actions/runner/releases/latest)
asset=$(jq -ce '[.assets[] | select(.name | test("^actions-runner-linux-x64-[0-9.]+[.]tar[.]gz$"))] | if length == 1 then .[0] else error("expected one Linux x64 archive") end' <<< "$release")
archive="$runner_root/downloads/$(jq -r .name <<< "$asset")"
digest=$(jq -er '.digest | select(startswith("sha256:")) | ltrimstr("sha256:")' <<< "$asset")
curl -fL "$(jq -r .browser_download_url <<< "$asset")" -o "$archive"
printf '%s  %s\n' "$digest" "$archive" | sha256sum -c -
```

Add a runner using an unused name and directory. `mkdir` intentionally fails if
the installation already exists. Do not copy `.runner` or `.credentials` from
another runner and do not use `--replace` during routine expansion:

```bash
runner_name=codex-reviewer-6
runner_dir="$runner_root/$runner_name"
mkdir "$runner_dir"
tar xzf "$archive" -C "$runner_dir"
cd "$runner_dir"
runner_token=$(gh api -X POST orgs/mobilint/actions/runners/registration-token --jq .token)
./config.sh --unattended --url https://github.com/mobilint \
  --token "$runner_token" --runnergroup codex --name "$runner_name" \
  --labels codex-reviewer --work _work
unset runner_token
printf '%s' "$runner_root/bin:$HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" > .path
sudo ./svc.sh install "$(id -un)"
sudo ./svc.sh start
systemctl is-enabled "actions.runner.mobilint.$runner_name.service"
systemctl is-active "actions.runner.mobilint.$runner_name.service"
gh api orgs/mobilint/actions/runner-groups/3/runners \
  --jq '.runners[] | {id,name,status,busy,labels}'
PATH="$runner_root/bin:$PATH" codex sandbox sh -lc true
```

Expect the exact name online, with the `codex-reviewer` label and a boot-enabled
service. No server reboot or workflow edit is needed. Use `journalctl -u
"actions.runner.mobilint.$runner_name.service"` for service logs, and `sudo
systemctl restart "actions.runner.mobilint.$runner_name.service"` after changes
that require restarting a service. Let an active review finish before restart.

Run **Check reviewer runner pool** from the repository's default branch. Select
1–5 slots (default 5); optionally enable **authenticated_smoke** to make a small
Luna/max request on each selected runner. This uses account quota. Compare job
runner names and overlapping timestamps: five completed jobs alone do not prove
five distinct runners, since a busy pool can reuse runners. Both planning and
self-hosted allocation reject non-default branches and other repositories.
Readiness validates required tools and sandbox startup; the optional request
also validates authentication/model access without publishing a review.

For removal, first pause new review submissions and wait until the exact runner
shows `busy: false`. An idle check alone cannot prevent an assignment racing
with service shutdown. Never stop a busy runner during routine removal:

```bash
runner_name=codex-reviewer-5
runner_root="$HOME/codex-runners"
gh api orgs/mobilint/actions/runner-groups/3/runners \
  --jq '.runners[] | {id,name,status,busy}'
cd "$runner_root/$runner_name"
sudo ./svc.sh stop
sudo ./svc.sh uninstall
runner_token=$(gh api -X POST orgs/mobilint/actions/runners/remove-token --jq .token)
./config.sh remove --token "$runner_token"
unset runner_token
gh api orgs/mobilint/actions/runner-groups/3/runners \
  --jq '.runners[] | {id,name,status,busy}'
```

Confirm the runner disappears from GitHub and its service is uninstalled. Its
local work directory remains; archive or delete that exact installation only
after checking that no service or job uses it. Keep `bin/` and all other runner
installations. If a host is permanently unavailable, an admin may delete the
exact registration with `gh api -X DELETE orgs/mobilint/actions/runners/ID`.
API deletion does not stop or uninstall a local service; clean that up when
host access becomes available.

### Pending central promotion

The proposed action pin is `8160555183d4cea8fccb0fdeb465681513afabf8`
from [action PR #17](https://github.com/mobilint/codex-review-action/pull/17).
This is a candidate, not a claim of deployed or reviewed behavior. Keep this
central PR draft until the action is reviewed/merged and the exact candidate
passes direct auto and mention canaries. If squash/rebase changes the candidate
SHA, update the pin and repeat the exact-SHA checks. Record the canary links in
the central PR, then review the promotion. After merge, validate central routing
at its resulting SHA before advancing the canonical template again or running
consumer synchronization. The caller update in this PR targets only the already
merged quota-fallback workflow, not this pending central candidate.
