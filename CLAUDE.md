# Claude Agent Guidance

This repository includes a local copy of `addyosmani/agent-skills` for Claude Code.

## Skill Discovery

Claude Code discovers project skills from `.claude/skills/<skill-name>/SKILL.md`.
Each skill has YAML front matter with `name` and `description`, followed by the
workflow instructions Claude should follow when the skill applies.

## How To Work

1. Start with `.claude/skills/using-agent-skills/SKILL.md`.
2. Match the user's intent to the relevant skill.
3. Load and follow that skill before implementing.
4. Use supporting files in the same skill directory when referenced by `SKILL.md`.

## Core Skill Map

- New feature or significant change: `spec-driven-development`
- Planning or task breakdown: `planning-and-task-breakdown`
- Implementation: `incremental-implementation` and `test-driven-development`
- Bug or failing behavior: `debugging-and-error-recovery`
- Code review: `code-review-and-quality`
- Refactoring or simplification: `code-simplification`
- API or interface work: `api-and-interface-design`
- Security-sensitive work: `security-and-hardening`
- Release work: `shipping-and-launch`

Cursor uses `.cursor/skills` plus `.cursor/rules`, and GitHub Copilot uses
`.github/skills`. Keep skill updates mirrored across all three platform folders.