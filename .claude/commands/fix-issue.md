---
name: fix-issue
argument-hint: [issue-number]
---

Fix GitHub issue #$ARGUMENTS:
1. `gh issue view $ARGUMENTS` — read the full issue
2. Identify the relevant source files in `server/` or `mobile/`
3. Implement the minimal fix — no extra changes
4. Write a regression test in pytest (server) or jest (mobile)
5. Run `pytest --tb=short -q` (server) or `npx jest` (mobile) — all green
6. Commit: `fix: <description> (closes #$ARGUMENTS)`
