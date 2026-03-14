# Live Verification Auth

## When to Use
Before any live verification that requires authentication (testing protected endpoints, checking pages that need login, verifying admin functionality). Use this skill whenever you get a 403/401 error during testing or need to access authenticated pages.

## Input
No input needed — credentials are stored in project memory.

## Steps

1. **Read credentials** from memory file: `memory/reference_test_credentials.md` in the project memory directory (`/home/dudka/.claude/projects/-home-dudka-chaldea/memory/reference_test_credentials.md`).

2. **Get JWT token** by calling the login endpoint:
```bash
TOKEN=$(curl -s -X POST http://localhost/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "chaldea@admin.com", "password": "123123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

3. **Use the token** in all subsequent requests:
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost/endpoint
```

4. **For browser/DevTools verification**, set the token in localStorage:
```javascript
// In browser console or via chrome-devtools MCP
localStorage.setItem('token', '<TOKEN_VALUE>');
// Then reload the page
```

## Result
- A valid JWT token that can be used for authenticated API calls
- The token works for admin-level access

## Agents
- **Primary:** Reviewer (live verification during review)
- **Secondary:** QA Test, Frontend Developer, Backend Developer (any agent doing live testing)
