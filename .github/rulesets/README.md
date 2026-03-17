# Branch and Tag Rulesets

## tags.json

Tag protection ruleset for `v*` version tags.

### Applying

GitHub UI → Settings → Rules → Rulesets → Import a ruleset → select `tags.json`.

### Rules

| Rule | Purpose |
|------|---------|
| `deletion` | Prevent version tags from being deleted |
| `non_fast_forward` | Tags are immutable — no moving an existing tag to a new commit |
| `required_signatures` | All tags must be GPG or SSH signed |

This ruleset prevents unauthorized release tags from being created (since `v*` tags
can trigger publish workflows) and ensures tags cannot be silently moved or removed
after a release.

---

## main.json

Branch protection ruleset for the `main` branch.

### Applying

GitHub UI → Settings → Rules → Rulesets → Import a ruleset → select `main.json`.

After importing, verify the required status checks are sourced from **GitHub Actions**
in the UI (the `integration_id` targets the GitHub Actions app but should be confirmed
after import).

### Rules

| Rule | Purpose |
|------|---------|
| `deletion` | Prevent direct deletion of the main branch |
| `non_fast_forward` | Prevent force-pushes, preserving linear history |
| `pull_request` | All changes must arrive via PR; no approvals required (solo project) but CI must run |
| `required_status_checks` | CI must pass before merging (see below) |
| `required_linear_history` | Squash or rebase merges only — keeps `git log` and `git bisect` clean |
| `required_signatures` | All commits must be GPG or SSH signed |

### Required status checks

| Check name | Workflow job | Purpose |
|------------|-------------|---------|
| `Tests passed` | `tests-passed` | Aggregates all matrix test jobs and the lint job |
| `Coverage report` | `coverage` | Combines and reports coverage across all matrix jobs |

`Tests passed` is a summary job so that adding new OS or Python versions to the
matrix does not require updating this ruleset. See `.github/workflows/ci.yaml`
job `tests-passed` for details.

### Updating

If you add a required status check or rename a CI job, update `main.json` and
re-import via Settings → Rules → Rulesets, or apply the change manually in the UI.