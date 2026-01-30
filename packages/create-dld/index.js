#!/usr/bin/env node

import { execSync } from 'child_process';
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';

const REPO_URL = 'https://github.com/Ellevated/dld.git';
const TEMPLATE_DIR = 'template';

// Check Node version
const [major] = process.versions.node.split('.');
if (parseInt(major) < 18) {
  console.error('Error: Node.js 18+ required (current: ' + process.versions.node + ')');
  process.exit(1);
}

// Check git availability
try {
  execSync('git --version', { stdio: 'pipe' });
} catch {
  console.error('Error: git is not installed. Please install git first.');
  process.exit(1);
}

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
    const msg = error.message || '';
    if (msg.includes('ENOTFOUND') || msg.includes('getaddrinfo')) {
      console.error('Error: Network unavailable. Check your internet connection.');
    } else if (msg.includes('Repository not found') || msg.includes('not found')) {
      console.error('Error: Could not access DLD repository. Please try again later.');
    } else {
      console.error('Error:', msg);
    }
    try {
      execSync(`rm -rf ${tempDir} ${projectName} 2>/dev/null`, { stdio: 'pipe' });
    } catch {}
    process.exit(1);
  }
}

main();
