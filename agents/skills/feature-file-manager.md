# Feature File Manager

## When to Use

When creating, updating, or closing feature files in the `features/` directory.

## Input

- Action: create / update / close
- For create: feature name, description, priority
- For update: file path, section to update, content
- For close: file path, completion summary

## Naming Convention

```
features/FEAT-{NNN}-{slug}.md          # Active feature
features/DONE-FEAT-{NNN}-{slug}.md     # Completed feature
```

- `{NNN}` — three-digit number (001, 002, ...)
- `{slug}` — short name with hyphens (add-guild-system, fix-battle-hp)

## Steps

### Create

1. Check existing files in `features/` to determine the next number
2. Copy the template from `features/FEAT-000-template.md`
3. Fill in the Meta section: status=OPEN, date, priority
4. Fill in section 1 (Feature Brief) based on user requirements (in Russian)
5. Save as `features/FEAT-{NNN}-{slug}.md`

### Update

Status transitions:
```
OPEN → IN_PROGRESS    (when Architect has broken down tasks)
IN_PROGRESS → REVIEW  (when all tasks are DONE, Reviewer launched)
REVIEW → IN_PROGRESS  (if Reviewer returned FAIL)
REVIEW → DONE         (if Reviewer returned PASS)
```

Section updates:
- Section 2 (Analysis Report) — filled by Codebase Analyst (English)
- Section 3 (Architecture Decision) — filled by Architect (English)
- Section 4 (Tasks) — filled by Architect, updated by PM (English)
- Section 5 (Review Log) — filled by Reviewer (English)
- Section 6 (Logging) — filled by all agents (Russian)

### Close

1. Fill in section 7 (Completion Summary) in Russian
2. Set status=DONE in Meta
3. Rename file: `FEAT-{NNN}-{slug}.md` → `DONE-FEAT-{NNN}-{slug}.md`

## Result

- Feature file created/updated/closed
- Status is current
- All sections filled by the corresponding agents

## Agents

- **Primary:** Orchestrator (PM)
