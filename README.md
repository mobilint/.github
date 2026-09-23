<div align="center">
<p>
<a href="https://www.mobilint.com/" target="_blank">
<img src="https://raw.githubusercontent.com/mobilint/.github/main/assets/Mobilint_Logo_Primary.png" alt="Mobilint Logo" width="60%">
</a>
</p>
</div>

[![GitHub clones](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmobilint%2F.github%2Fbadges%2F.github%2Fbadges%2Fclones.json)](https://github.com/mobilint/.github/graphs/traffic)

# Mobilint shared GitHub automation

This repository provides Mobilint's shared GitHub workflow templates and
centrally managed Codex pull-request review policy.

Consumer repositories use a small
`.github/workflows/code-review.yml` caller. Review limits, trust checks,
official-Codex fallback behavior, reactions, sandbox policy, and runner
selection remain in the central reusable workflow, so routine policy updates
do not require hand-editing every repository.

The managed caller supports:

- automatic review for trusted pull-request authors;
- direct `@mobilint-review` requests from trusted commenters in PR comments,
  review comments, and submitted review bodies;
- temporary 👀 acknowledgement, removed even when a queued review is canceled,
  followed by a review, visible error, or 👍 for a clean result;
- central P0/P1/P2 review findings on the self-hosted Codex reviewer.

The official workflow template is
[`workflow-templates/code-review.yml`](workflow-templates/code-review.yml).
Its central `.github/workflows/code-review.yml` example is synchronized
automatically. Mobilint maintainers still copy the caller into consumer
repositories. The manifest and local audit tool help detect consumer drift, but
no unattended cross-repository credential workflow is installed.

Maintainers should use the
[automation operations guide](.github/MAINTAINERS.md) for architecture, enrollment,
manual synchronization, validation, release, and rollback procedures.

The reusable workflow pins the review action to an immutable commit and forwards
the mode selected by its event gate. Direct action users may omit `mode` to infer
`auto` for pull requests or `mention` for comment/review events.

The reusable workflow always uses the read-only sandbox and disables unsafe
fallback. The deprecated `allow_unsafe_no_sandbox_fallback` input is accepted
for compatibility but ignored, regardless of its value.

Caller audits also inspect existing automation branches when the default caller
is current. Synchronization rejects symlink callers and repairs untrusted
automation branch changes before retaining managed PR metadata.

Codex and Claude share repository guidance through symlinks: edit `AGENTS.md`
and `.agents/skills`; `CLAUDE.md` and `.claude/skills` use those same files.
