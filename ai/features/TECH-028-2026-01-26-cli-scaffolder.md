# Feature: [TECH-028] CLI Scaffolder (npx create-dld)

**Status:** done | **Priority:** P1 | **Date:** 2026-01-26

## Why

Current setup requires manual copy-paste:
```bash
git clone https://github.com/Ellevated/dld
mkdir my-project && cd my-project
cp -r ../dld/template/* .
cp -r ../dld/template/.claude .
```

Modern expectation:
```bash
npx create-dld my-project
cd my-project
claude
```

Lower barrier = more users = more stars.

---

## Scope

**In scope:**
- Create `create-dld` npm package
- Copy template files to target directory
- Initialize git repository
- Show next steps

**Out of scope:**
- Python version (pipx) — can add later
- Interactive prompts — keep it simple
- Template customization — one template for now

---

## Impact Tree Analysis

### Step 1: New package structure
```
packages/
└── create-dld/
    ├── package.json
    ├── index.js
    └── README.md
```

### Step 2: Template location
- Current: `template/` in repo root
- For npm: bundle in package or fetch from GitHub

### Decision: Fetch from GitHub
- Smaller npm package
- Always latest template
- No version sync issues

---

## Allowed Files

**New files allowed:**
1. `packages/create-dld/package.json` — npm package config
2. `packages/create-dld/index.js` — main script
3. `packages/create-dld/README.md` — package docs

**Modify:**
4. `README.md` — update Quick Start section

**FORBIDDEN:** All other files.

---

## Environment

nodejs: true
docker: false
database: false

---

## Design

### `packages/create-dld/package.json`:
```json
{
  "name": "create-dld",
  "version": "1.0.0",
  "description": "Create a new DLD project with Claude Code",
  "bin": {
    "create-dld": "./index.js"
  },
  "type": "module",
  "keywords": ["dld", "claude", "ai", "scaffolding"],
  "repository": {
    "type": "git",
    "url": "https://github.com/Ellevated/dld"
  },
  "license": "MIT"
}
```

### `packages/create-dld/index.js`:
```javascript
#!/usr/bin/env node

import { execSync } from 'child_process';
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';

const REPO_URL = 'https://github.com/Ellevated/dld.git';
const TEMPLATE_DIR = 'template';

async function main() {
  const projectName = process.argv[2];

  if (!projectName) {
    console.log('Usage: npx create-dld <project-name>');
    process.exit(1);
  }

  if (existsSync(projectName)) {
    console.error(`Error: Directory '${projectName}' already exists`);
    process.exit(1);
  }

  console.log(`Creating DLD project: ${projectName}`);

  // Clone template (sparse checkout)
  const tempDir = `.dld-temp-${Date.now()}`;

  try {
    execSync(`git clone --depth 1 --filter=blob:none --sparse ${REPO_URL} ${tempDir}`, { stdio: 'pipe' });
    execSync(`git -C ${tempDir} sparse-checkout set ${TEMPLATE_DIR}`, { stdio: 'pipe' });

    // Move template to project
    mkdirSync(projectName);
    execSync(`cp -r ${tempDir}/${TEMPLATE_DIR}/. ${projectName}/`, { stdio: 'pipe' });

    // Initialize git
    execSync(`git -C ${projectName} init`, { stdio: 'pipe' });

    // Cleanup
    execSync(`rm -rf ${tempDir}`, { stdio: 'pipe' });

    console.log(`
✓ Project created: ${projectName}

Next steps:
  cd ${projectName}
  claude
  /bootstrap
    `);
  } catch (error) {
    console.error('Error:', error.message);
    execSync(`rm -rf ${tempDir} ${projectName}`, { stdio: 'pipe' });
    process.exit(1);
  }
}

main();
```

### Updated README.md Quick Start:
```markdown
## Quick Start

### Option 1: NPX (Recommended)
\`\`\`bash
npx create-dld my-project
cd my-project
claude
/bootstrap
\`\`\`

### Option 2: Manual
\`\`\`bash
git clone https://github.com/Ellevated/dld
mkdir my-project && cd my-project
cp -r ../dld/template/* .
cp -r ../dld/template/.claude .
claude
/bootstrap
\`\`\`
```

---

## Implementation Plan

### Task 1: Create package.json
**Type:** create
**Files:** create `packages/create-dld/package.json`
**Acceptance:**
- [ ] Valid npm package config
- [ ] Correct bin entry

### Task 2: Create main script
**Type:** create
**Files:** create `packages/create-dld/index.js`
**Acceptance:**
- [ ] Accepts project name argument
- [ ] Clones template from GitHub
- [ ] Initializes git repo
- [ ] Shows next steps

### Task 3: Create package README
**Type:** create
**Files:** create `packages/create-dld/README.md`
**Acceptance:**
- [ ] Usage instructions
- [ ] Links to main docs

### Task 4: Update main README
**Type:** edit
**Files:** modify `README.md`
**Acceptance:**
- [ ] NPX option listed first
- [ ] Manual option still available

### Execution Order
1 → 2 → 3 → 4

---

## Post-Implementation

**Manual steps after merge:**
1. `cd packages/create-dld`
2. `npm publish --access public`
3. Test: `npx create-dld test-project`

---

## Definition of Done

### Functional
- [ ] `npx create-dld my-project` works
- [ ] Creates correct directory structure
- [ ] Shows helpful next steps

### Technical
- [ ] No npm publish errors
- [ ] Works on macOS, Linux, Windows (WSL)
