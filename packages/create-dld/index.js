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
