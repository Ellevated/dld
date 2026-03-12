# Tech: [TECH-050] Improve NPM package quality

**Status:** done | **Priority:** P1 | **Date:** 2026-01-30

## Problem

`packages/create-dld/package.json` is missing important fields:
- No `author`
- No `engines` (Node version requirement)
- No `files` (may publish unnecessary files)

`packages/create-dld/index.js` lacks basic validation:
- No Node version check
- No git availability check
- Poor error messages for network failures

## Solution

1. Add missing package.json fields
2. Add runtime checks to index.js

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `packages/create-dld/package.json` | modify | Add missing fields |
| 2 | `packages/create-dld/index.js` | modify | Add runtime checks |

## Tasks

### Task 1: Complete package.json

**Files:** `packages/create-dld/package.json`

**Steps:**
1. Add `"author": "DLD Contributors"`
2. Add `"engines": { "node": ">=18.0.0" }`
3. Add `"files": ["index.js", "README.md"]`

**Acceptance:**
- [ ] All recommended fields present
- [ ] engines specifies Node 18+

### Task 2: Add runtime checks to index.js

**Files:** `packages/create-dld/index.js`

**Steps:**
1. Add Node version check at start:
   ```javascript
   const [major] = process.versions.node.split('.');
   if (parseInt(major) < 18) {
     console.error('Error: Node.js 18+ required');
     process.exit(1);
   }
   ```
2. Add git check before clone:
   ```javascript
   try {
     execSync('git --version', { stdio: 'pipe' });
   } catch {
     console.error('Error: git is not installed');
     process.exit(1);
   }
   ```
3. Improve error message in catch block to show friendly network error

**Acceptance:**
- [ ] Fails gracefully without git
- [ ] Fails gracefully on old Node
- [ ] Clear error messages

## DoD

- [ ] package.json has author, engines, files
- [ ] index.js validates environment
- [ ] Error messages are helpful
