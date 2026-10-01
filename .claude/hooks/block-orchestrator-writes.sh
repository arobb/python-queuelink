#!/usr/bin/env bash
# PreToolUse hook (Edit|Write|NotebookEdit): keeps the top-level ("L0") Claude
# Code session from writing product files directly. L0 plans and delegates
# implementation to subagents; only they may write these paths. See AGENTS.md
# "Agent Roles (L0/L1)".
#
# Subagent tool calls carry an "agent_id" field in the hook payload that the
# top-level session's own calls never have (verified empirically), so that
# field is what distinguishes "L0 acting directly" from "a delegated L1".
set -euo pipefail

input=$(cat)

agent_id=$(printf '%s' "$input" | jq -r '.agent_id // empty')
if [[ -n "$agent_id" ]]; then
  exit 0
fi

file_path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')
if [[ -z "$file_path" ]]; then
  exit 0
fi

cwd=$(printf '%s' "$input" | jq -r '.cwd // empty')
rel_path=$file_path
if [[ -n "$cwd" && "$file_path" == "$cwd"/* ]]; then
  rel_path=${file_path#"$cwd"/}
fi

case "$rel_path" in
  src/*|tests/*|benchmarks/*|docs/*|README.rst|CHANGELOG.rst|setup.py|setup.cfg|pyproject.toml|requirements*.txt)
    jq -n --arg path "$rel_path" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("L0 does not edit product files directly (" + $path + "). Delegate this to an implementation subagent per AGENTS.md § Agent Roles (L0/L1).")
      }
    }'
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
