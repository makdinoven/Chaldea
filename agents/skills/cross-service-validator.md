# Cross-Service Validator

## When to Use

For any changes affecting inter-service communication: new endpoints, modified request/response schemas, changed URLs/ports, new HTTP calls between services.

## Input

- List of affected services and modified files
- HTTP dependency graph from `CLAUDE.md` section 2

## Steps

### 1. Build the affected dependency graph

From `CLAUDE.md` section 2, extract only the links that involve the modified services:

```
character-service ──> inventory-service, skills-service, character-attributes-service, user-service
locations-service ──> character-service, character-attributes-service
inventory-service ──> character-attributes-service
battle-service ──> character-attributes-service, character-service, skills-service, inventory-service
autobattle-service ──> battle-service
user-service ──> character-service, locations-service
notification-service ──> user-service
```

### 2. Find all HTTP calls to/from affected services

```bash
# Find outgoing calls (httpx, requests)
grep -rn "httpx\.\|requests\.\|\.get(\|\.post(\|\.put(\|\.delete(" services/<service>/app/

# Find URL patterns
grep -rn "http://\|localhost:\|:80[0-9][0-9]" services/<service>/app/

# Frontend: find API calls
grep -rn "axios\.\|api\.\|fetch(" services/frontend/app-chaldea/src/
```

### 3. Verify consistency of each call

For each found HTTP call, verify:

| Check | How |
|-------|-----|
| URL is correct | Port matches the port table in CLAUDE.md |
| Path exists | Endpoint is declared in `main.py` of the called service |
| HTTP method matches | GET/POST/PUT/DELETE matches |
| Request body | Fields and types match the Pydantic schema of the called endpoint |
| Response format | Calling code expects the same fields that the called endpoint returns |
| Error handling | Is 404/500 from the called service handled? |

### 4. Verify backward compatibility

If an existing endpoint is modified:
- Find all services that call it (grep by URL/path)
- Ensure they won't break from the changes
- New required fields in request = breaking change

### 5. Verify shared DB

If a table is modified:
- Find all services that read/write to this table
- `grep -rn "table_name" services/*/app/models.py`
- photo-service: `grep -rn "table_name" services/photo-service/app/main.py` (raw SQL)

## Result

Table of verified contracts:

| Caller | Callee | Endpoint | Status | Issue (if any) |
|--------|--------|----------|--------|----------------|
| character-service | inventory-service | GET /inventory/{id} | OK | — |
| frontend | character-service | POST /characters/ | FAIL | Field `race_id` renamed |

## Agents

- **Primary:** Reviewer — final contract verification
- **Secondary:** Codebase Analyst — during dependency analysis
