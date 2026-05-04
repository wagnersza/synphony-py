# GitHub Copilot Instructions

This repository includes `addyosmani/agent-skills` for Copilot under
`.github/skills/<skill-name>/SKILL.md`.

## Skill Use

- Check `.github/skills/using-agent-skills/SKILL.md` at the start of a task.
- If the task maps to a skill, follow that skill's workflow before coding.
- Load supporting files from the same skill directory only when the skill points to them.
- Do not skip verification gates in the applicable skill.

## Common Mappings

- Feature or significant behavior change: `spec-driven-development`
- Planning: `planning-and-task-breakdown`
- Implementation: `incremental-implementation` and `test-driven-development`
- Bug fix: `debugging-and-error-recovery`, then `test-driven-development`
- Review: `code-review-and-quality`
- Simplification: `code-simplification`
- API/interface design: `api-and-interface-design`
- Security-sensitive work: `security-and-hardening`
- Release preparation: `shipping-and-launch`

The same skill pack is mirrored for Claude in `.claude/skills` and for Cursor in
`.cursor/skills`, with selected always-loaded Cursor rules in `.cursor/rules`.
