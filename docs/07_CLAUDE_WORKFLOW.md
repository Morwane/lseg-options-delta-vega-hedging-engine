# 07 — Claude Code Workflow for This Project

This file is based on current Claude Code behavior and best practices as of 2026.

## Recommended way to use Claude Code

Use Claude Code inside VS Code or from the terminal.

### Option A — VS Code extension

Use the Claude Code VS Code extension if you want:

- inline diffs
- plan review before edits
- @-mentions for selected files/line ranges
- checkpoints and rewind
- multiple sessions in tabs

### Option B — terminal CLI

From the project folder:

```bash
claude
```

Useful commands:

```text
/init        Generate or refresh CLAUDE.md
/plan        Use planning mode if available in your interface
/agents      Manage subagents
/permissions Configure allowed commands/tools
/rewind      Revert to checkpoints
/compact     Compress context when it grows too large
```

## How to prompt Claude on this repo

Use file references instead of re-explaining everything:

```text
Read @CLAUDE.md and @docs/03_IMPLEMENTATION_PLAN.md. Implement Phase 2 only. Run pytest for pricing tests and fix failures.
```

## Best sequence for a phase

1. Put Claude in Plan Mode.
2. Ask it to read the relevant docs.
3. Ask for a plan and files to modify.
4. Approve the plan.
5. Switch to implementation.
6. Ask it to run exact tests.
7. Ask it to summarize changed files and remaining issues.

## Keep context under control

Claude performance can degrade when the context window fills. Do not paste long terminal logs unless needed. Save logs to files and reference them with `@outputs/logs/...`.

Use focused prompts:

```text
Implement only src/pricing/black_scholes.py and tests/test_black_scholes.py.
```

Avoid broad prompts like:

```text
Finish the whole project.
```

## Use subagents for investigation

For read-heavy tasks, ask:

```text
Use a subagent to inspect the repo structure and identify missing tests. Report back, but do not modify files yet.
```

Good use cases:

- audit code structure
- review safety constraints
- search for hard-coded credentials
- review tests for missing cases
- inspect README consistency

## Use skills for repeatable playbooks

This handoff includes a project skill at:

```text
.claude/skills/hedging-engine/SKILL.md
```

It gives Claude a reusable playbook for this project. Invoke it directly with:

```text
/hedging-engine
```

or let Claude load it when relevant.

## Verification-first prompting

Always give Claude the verification command:

```text
After coding, run pytest -q and python scripts/run_demo.py. Fix failures. Report final output.
```

Claude works much better when it can verify its own work.

## Safe working prompts

### Prompt 1 — structure only

```text
Read @CLAUDE.md and @docs/02_ARCHITECTURE.md. Create only the folder structure, config files, pyproject.toml, requirements.txt, and package __init__.py files. Do not implement logic yet. Run python -m compileall src scripts.
```

### Prompt 2 — pricing only

```text
Read @docs/04_MODULE_SPECS.md. Implement only src/pricing/black_scholes.py, src/pricing/implied_vol.py, tests/test_black_scholes.py, and tests/test_implied_vol.py. Run pytest -q tests/test_black_scholes.py tests/test_implied_vol.py.
```

### Prompt 3 — portfolio/exposures only

```text
Implement only portfolio dataclasses, YAML portfolio loading, exposure aggregation, and tests. Do not touch IBKR or LSEG yet. Run pytest -q tests/test_exposures.py and python scripts/run_demo.py.
```

### Prompt 4 — daily hedge dry-run

```text
Implement IBKR dry-run mode only. Connect to paper TWS on port 7497, request delayed market data, read positions, and print recommended hedge orders. Do not place orders. Run python scripts/run_daily_hedge.py --dry-run.
```

### Prompt 5 — paper execution later

```text
Implement paper execution mode with explicit --paper-execute flag and manual y/N confirmation. Do not implement live trading. Log all orders to outputs/executions/. Add tests for blocked/live-disabled behavior.
```
