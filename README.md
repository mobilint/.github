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
- direct `@mobilint-review` requests in PR comments, review comments, and
  submitted review bodies;
- temporary 👀 acknowledgement followed by a review, visible error, or 👍 for
  a clean result;
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
