# HARNESS.md

This project uses a harness engineering approach to AI-assisted development.
The goal is to make the repository itself the primary interface for AI agents:
clear instructions, automated feedback loops, and guardrails that apply equally
to human and agent contributors.

## Principles

1. **The repo is the prompt.** Agents receive project context from files checked
   into the repository, not from chat history or external configuration. This
   keeps instructions versioned, reviewable, and consistent across tools.

2. **CI is the feedback loop.** Agents validate their own work by running the
   same test suite, linters, and checks that humans use. A passing CI pipeline
   is the primary quality signal — not self-reported confidence.

3. **One set of rules.** Agent instructions, coding conventions, and pitfall
   documentation live in a single canonical file (`AGENTS.md`). Tool-specific
   files (e.g., `CLAUDE.md`) reference it rather than duplicating it.

4. **Same gates for everyone.** PRs from agents go through the same branch
   protection, CI checks, and review process as human PRs. No shortcuts.

## File inventory

| File | Read by | Purpose |
|---|---|---|
| `AGENTS.md` | AI agents (Codex, Copilot, etc.) | Canonical project instructions: build commands, architecture, coding conventions, pitfalls, CI/CD, PR workflow |
| `.claude/CLAUDE.md` | Claude Code | Pointer to `AGENTS.md` (Claude Code requires this filename; `.gitignore` exception allows tracking) |
| `.github/copilot-instructions.md` | GitHub Copilot | Pointer to `AGENTS.md` |
| `.cursor/rules/read-agent-instructions.md` | Cursor | Pointer to `AGENTS.md` |
| `.aiassistant/rules/read-agent-instructions.md` | JetBrains AI Assistant | Pointer to `AGENTS.md` |
| `HARNESS.md` | Humans | This file — explains the approach and file layout |
| `.pre-commit-config.yaml` | pre-commit / git hooks | Local guardrails: whitespace, EOF, YAML/TOML validation, bandit |
| `.github/workflows/ci.yaml` | GitHub Actions | Remote guardrails: 25-job test matrix, lint, coverage |
| `.github/workflows/publish.yaml` | GitHub Actions | OIDC trusted publishing to PyPI |
| `.github/rulesets/` | GitHub | Branch/tag protection — enforces PR workflow, linear history, signed commits |
| `setup.cfg` | tox, pytest, coverage, pylint | Test configuration, lint rules, coverage settings |

## How it works in practice

```
Developer or agent makes changes
        │
        ▼
pre-commit hooks (local)
  ├─ trailing whitespace, EOF fixer
  ├─ YAML/TOML validation
  └─ bandit security scan
        │
        ▼
Push branch → open PR
        │
        ▼
CI pipeline (remote)
  ├─ 25-job test matrix (5 OS × 5 Python)
  ├─ pylint + bandit lint
  └─ coverage reporting
        │
        ▼
Branch ruleset enforcement
  ├─ CI must pass
  ├─ Squash or rebase merge only
  └─ Signed commits on main
        │
        ▼
Merged to main
```

## Maintaining these files

- **`AGENTS.md` is the single source of truth** for agent instructions. When
  project conventions, architecture, or pitfalls change, update `AGENTS.md`.
  Do not duplicate this content into `CLAUDE.md` or other tool-specific files.

- **Add tool-specific files only when a tool requires a specific filename**
  (as Claude Code requires `CLAUDE.md`). Keep them minimal — a reference to
  `AGENTS.md` plus any tool-specific configuration that cannot live elsewhere.

- **Update the file inventory table above** when adding or removing harness
  files so this document remains a reliable map for new contributors.
