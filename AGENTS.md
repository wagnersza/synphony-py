# AGENTS.md

Guidance for AI coding agents working in **synphony-py** using **Claude Code, Cursor, or GitHub Copilot**.

## Repository Overview

**synphony-py** is a Python implementation of the Symphony orchestrator (issue-tracker polling, per-issue workspaces, coding-agent runners). Engineering workflow guidance comes from the local copy of [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills), mirrored into each supported agent's discovery path.

## Platform integrations

- **Claude Code:** project skills live in `.claude/skills/<skill-name>/SKILL.md`; `CLAUDE.md` is the project entrypoint.
- **Cursor:** full skills live in `.cursor/skills/<skill-name>/SKILL.md`; selected always-loaded rules live in `.cursor/rules/*.md`.
- **GitHub Copilot:** project skills live in `.github/skills/<skill-name>/SKILL.md`; `.github/copilot-instructions.md` is the project entrypoint.

Keep skill content mirrored across `.claude/skills/`, `.cursor/skills/`, and `.github/skills/` when updating or adding skills.

## Cursor integration

Cursor applies Markdown files from `.cursor/rules/` as project context. Open or `@`-reference `.cursor/skills/<skill-name>/SKILL.md` when a skill applies but is not one of the always-loaded rules.

## Claude Code integration

Claude Code auto-discovers project skills from `.claude/skills/`. Start with `.claude/skills/using-agent-skills/SKILL.md`, then invoke or load the matching skill by name when the user's task matches its description.

## GitHub Copilot integration

Copilot discovers repository skills from `.github/skills/` and also reads `.github/copilot-instructions.md`. Use the skill directory as the detailed workflow source and keep the Copilot instructions concise.

### Core rules

- If a task matches a skill, follow that skill’s workflow before improvising.
- Prefer the native skill directory for the current tool; in Cursor, prefer rules already in `.cursor/rules/` and use `.cursor/skills/` for additional skills.
- Do not partially apply a skill when it applies to the task.

### Intent → skill mapping

Map user intent to skills (by rule name / `SKILL.md` folder):

- Feature / new functionality → `spec-driven-development`, then `incremental-implementation`, `test-driven-development`
- Planning / breakdown → `planning-and-task-breakdown`
- Bug / failure / unexpected behavior → `debugging-and-error-recovery`
- Code review → `code-review-and-quality`
- Refactoring / simplification → `code-simplification`
- API or interface design → `api-and-interface-design`
- UI work → `frontend-ui-engineering`

### Lifecycle

Claude Code may expose slash commands from the upstream plugin. Cursor and Copilot should treat the lifecycle as **implicit** in how they work:

- DEFINE → `spec-driven-development`
- PLAN → `planning-and-task-breakdown`
- BUILD → `incremental-implementation` + `test-driven-development`
- VERIFY → `debugging-and-error-recovery`
- REVIEW → `code-review-and-quality`
- SHIP → `shipping-and-launch`

### Execution model

For each request:

1. Decide if a skill applies (even partially).
2. Open the matching file from the current tool's skill path: `.claude/skills/`, `.cursor/skills/`, or `.github/skills/`. In Cursor, use `.cursor/rules/<name>.md` first when present.
3. Follow that workflow strictly.
4. Only implement after required steps (spec, plan, etc.) are satisfied when the skill demands them.

### Anti-rationalization

Ignore:

- "This is too small for a skill"
- "I can just quickly implement this"
- "I’ll gather context first"

Correct behavior: **check for an applicable skill first**, then implement.

More setup context: [Cursor](https://github.com/addyosmani/agent-skills/blob/main/docs/cursor-setup.md), [Copilot](https://github.com/addyosmani/agent-skills/blob/main/docs/copilot-setup.md), and [Claude Code skills](https://docs.anthropic.com/en/docs/claude-code/skills).

## Orchestration: Personas, Skills, and Commands

This repo has three composable layers. They have different jobs and should not be confused:

- **Skills** — in this repo, full copies live as `.claude/skills/<name>/SKILL.md`, `.cursor/skills/<name>/SKILL.md`, and `.github/skills/<name>/SKILL.md`; selected Cursor rules also live as `.cursor/rules/*.md`. The *how*. Mandatory hops when an intent matches.
- **Personas** — see [agents](https://github.com/addyosmani/agent-skills/tree/main/agents) in the upstream repo. The *who*.
- **Slash commands** — upstream `.claude/commands/*.md` (Claude Code). The *when*. The orchestration layer.

Composition rule: **the user (or a slash command) is the orchestrator. Personas do not invoke other personas.** A persona may invoke skills.

The only multi-persona orchestration pattern this repo endorses is **parallel fan-out with a merge step** — used by `/ship` to run `code-reviewer`, `security-auditor`, and `test-engineer` concurrently and synthesize their reports. Do not build a "router" persona that decides which other persona to call; that's the job of slash commands and intent mapping.

See the upstream [agents README](https://github.com/addyosmani/agent-skills/blob/main/agents/README.md) for the decision matrix and [orchestration-patterns.md](https://github.com/addyosmani/agent-skills/blob/main/references/orchestration-patterns.md) for the full pattern catalog.

**Claude Code interop:** the personas in `agents/` work as Claude Code subagents (auto-discovered from this plugin's `agents/` directory) and as Agent Teams teammates (referenced by name when spawning). Two platform constraints align with our rules: subagents cannot spawn other subagents, and teams cannot nest. Plugin agents silently ignore the `hooks`, `mcpServers`, and `permissionMode` frontmatter fields.

## Creating a New Skill

**In synphony-py:** add a new skill directory under each platform path: `.claude/skills/<skill-name>/SKILL.md`, `.cursor/skills/<skill-name>/SKILL.md`, and `.github/skills/<skill-name>/SKILL.md`. Add a matching `.cursor/rules/<skill-name>.md` only when that skill should be always loaded in Cursor. The paths below match the **upstream** repository layout for authors contributing to that project.

### Directory Structure

```
skills/
  {skill-name}/           # kebab-case directory name
    SKILL.md              # Required: skill definition
    scripts/              # Required: executable scripts
      {script-name}.sh    # Bash scripts (preferred)
  {skill-name}.zip        # Required: packaged for distribution
```

### Naming Conventions

- **Skill directory**: `kebab-case` (e.g. `web-quality`)
- **SKILL.md**: Always uppercase, always this exact filename
- **Scripts**: `kebab-case.sh` (e.g., `deploy.sh`, `fetch-logs.sh`)
- **Zip file**: Must match directory name exactly: `{skill-name}.zip`

### SKILL.md Format

```markdown
---
name: {skill-name}
description: {One sentence describing when to use this skill. Include trigger phrases like "Deploy my app", "Check logs", etc.}
---

# {Skill Title}

{Brief description of what the skill does.}

## How It Works

{Numbered list explaining the skill's workflow}

## Usage

```bash
bash /mnt/skills/user/{skill-name}/scripts/{script}.sh [args]
```

**Arguments:**

- `arg1` - Description (defaults to X)

**Examples:**
{Show 2-3 common usage patterns}

## Output

{Show example output users will see}

## Present Results to User

{Template for how Claude should format results when presenting to users}

## Troubleshooting

{Common issues and solutions, especially network/permissions errors}

```

### Best Practices for Context Efficiency

Skills are loaded on-demand — only the skill name and description are loaded at startup. The full `SKILL.md` loads into context only when the agent decides the skill is relevant. To minimize context usage:

- **Keep SKILL.md under 500 lines** — put detailed reference material in separate files
- **Write specific descriptions** — helps the agent know exactly when to activate the skill
- **Use progressive disclosure** — reference supporting files that get read only when needed
- **Prefer scripts over inline code** — script execution doesn't consume context (only output does)
- **File references work one level deep** — link directly from SKILL.md to supporting files

### Script Requirements

- Use `#!/bin/bash` shebang
- Use `set -e` for fail-fast behavior
- Write status messages to stderr: `echo "Message" >&2`
- Write machine-readable output (JSON) to stdout
- Include a cleanup trap for temp files
- Reference the script path as `/mnt/skills/user/{skill-name}/scripts/{script}.sh`

### Creating the Zip Package

After creating or updating a skill:

```bash
cd skills
zip -r {skill-name}.zip {skill-name}/
```

### End-User Installation

Document these two installation methods for users:

**Claude Code:**

```bash
cp -r skills/{skill-name} ~/.claude/skills/
```

**claude.ai:**
Add the skill to project knowledge or paste SKILL.md contents into the conversation.

If the skill requires network access, instruct users to add required domains at `claude.ai/settings/capabilities`.