---
name: codex
description: Delegate implementation work to OpenAI Codex CLI while Claude plans and reviews. Use when the user says "ให้ codex ทำ", "delegate to codex", "/codex", or asks for Claude-plans/Codex-executes mode.
---

# Claude plans, Codex executes

Codex CLI (0.169+) has no MCP server mode; drive it with `codex exec` through the shell.

## Workflow

1. **Plan (Claude).** Read `AGENTS.md` if present, then write or update `PLAN.md` in the repo root as a checklist:
   `- [ ] task | files to touch | how to verify`
   Keep each item small enough for one Codex run. Commit (or note `git status`) before delegating so changes can be reverted.
2. **Delegate (Codex).** For each item, or the whole plan, run from the repo root:

   ```
   codex exec -s workspace-write -C <repo> -o .codex_last.txt "Read AGENTS.md and PLAN.md. Do item: <item>. Run its verify step. Tick [x] in PLAN.md only if it passes. Do not touch files outside the listed ones."
   ```

   - Add `--skip-git-repo-check` if the folder is not a git repo.
   - Use `-s read-only` when only asking Codex for analysis or a second opinion.
   - Runs can take several minutes; use a long timeout (up to 600000 ms) or run in background.
   - Never use `--dangerously-bypass-approvals-and-sandbox` unless the user asks.
3. **Review (Claude).** Read `.codex_last.txt` and `git diff`, run the tests yourself, and fix or re-delegate with a precise correction. Report to the user what Codex did and what you verified.

## Mode switching

- "โหมด claude" / solo Claude: skip delegation, implement directly.
- "โหมด codex" / Codex only: pass the user's request to `codex exec` unchanged and report the result.
- "สลับ" / Codex plans, Claude executes: run `codex exec -s workspace-write ... "Write a plan for <task> to PLAN.md only, do not edit other files"`, then implement PLAN.md yourself.
- "ความเห็นที่สอง": `codex review` or `codex exec -s read-only "Review git diff against PLAN.md"`.

Never let Claude and Codex edit the same files at the same time.
