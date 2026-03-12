# Skills (Agent Skills)

Skills are reusable instructions that agents invoke for common operations.
Each skill is a separate `.md` file in this directory.

## Skill-to-Agent Mapping

| Skill | File | Primary Agent | Secondary Agent |
|-------|------|---------------|-----------------|
| API Design Spec | `api-design-spec.md` | Backend Developer | Architect |
| API Integration Test | `api-integration-test.md` | QA Test | — |
| FastAPI Endpoint Generator | `fastapi-endpoint-generator.md` | Backend Developer | — |
| Frontend Design | `frontend-design.md` | Frontend Developer | — |
| Redux Slice Generator | `redux-slice-generator.md` | Frontend Developer | — |
| TypeScript Expert | `typescript-expert.md` | Frontend Developer | Reviewer |
| Pytest Fixture Creator | `pytest-fixture-creator.md` | QA Test | — |
| WebSocket Handler | `websocket-handler.md` | Frontend Developer | Backend Developer |
| Python Developer | `python-developer.md` | Backend Developer | DevSecOps, Codebase Analyst |
| Cross-Service Validator | `cross-service-validator.md` | Reviewer | Codebase Analyst |
| Alembic Migration Guide | `alembic-migration-guide.md` | Backend Developer | — |
| Feature File Manager | `feature-file-manager.md` | Orchestrator (PM) | — |

## Skill File Format

```markdown
# Skill Name

## When to Use
Description of situations where the skill applies.

## Input
What needs to be passed to the skill.

## Steps
1. ...
2. ...

## Result
What the skill produces.

## Agents
- **Primary:** who uses it most often
- **Secondary:** who may use it when needed
```
