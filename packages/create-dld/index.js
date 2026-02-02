#!/usr/bin/env node

import { execSync, exec } from 'child_process';
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import prompts from 'prompts';

const REPO_URL = 'https://github.com/Ellevated/dld.git';
const TEMPLATE_DIR = 'template';

// MCP server commands
const MCP_SERVERS = {
  context7: {
    name: 'Context7',
    cmd: 'claude mcp add context7 -- npx -y @context7/mcp-server',
    test: 'npx -y @context7/mcp-server --help'
  },
  exa: {
    name: 'Exa',
    cmd: 'claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"',
    test: 'curl -s --max-time 5 "https://mcp.exa.ai/mcp" | head -c 1'
  }
};

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

async function addMcpServer(server) {
  return new Promise((resolve) => {
    console.log(`  Adding ${server.name}...`);
    exec(server.cmd, { timeout: 30000 }, (error) => {
      if (error) {
        console.log(`  Warning: ${server.name} setup may have issues`);
        resolve(false);
      } else {
        console.log(`  ${server.name} added`);
        resolve(true);
      }
    });
  });
}

async function setupMcp(tier) {
  if (tier === 0) {
    console.log('\nSkipping MCP setup. You can run ./scripts/setup-mcp.sh later.');
    return;
  }

  console.log('\nConfiguring MCP servers...');

  if (tier >= 1) {
    await addMcpServer(MCP_SERVERS.context7);
    await addMcpServer(MCP_SERVERS.exa);
  }

  if (tier >= 2) {
    console.log('\nTier 3 servers require API keys.');
    console.log('Run ./scripts/setup-mcp.sh --tier 3 to complete setup.');
  }

  console.log('\nMCP setup complete. Restart Claude Code to activate.');
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

    console.log(`\nProject created: ${projectName}`);

    // MCP setup prompt
    const response = await prompts({
      type: 'select',
      name: 'mcpTier',
      message: 'Configure MCP servers?',
      choices: [
        { title: 'Recommended (Context7 + Exa)', description: 'No API keys needed', value: 1 },
        { title: 'Skip for now', description: 'Run ./scripts/setup-mcp.sh later', value: 0 },
        { title: 'Power tier', description: 'Requires API keys (advanced)', value: 2 }
      ],
      initial: 0
    });

    // Handle Ctrl+C
    if (response.mcpTier === undefined) {
      console.log('\nSetup cancelled. Project created without MCP.');
    } else {
      await setupMcp(response.mcpTier);
    }

    console.log(`
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
