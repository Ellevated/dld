#!/usr/bin/env node

import { execSync, exec } from 'child_process';
import { existsSync, cpSync, rmSync } from 'fs';
import { join } from 'path';
import prompts from 'prompts';

// Validate project name to prevent shell injection
function isValidProjectName(name) {
  // Only allow: letters, numbers, hyphens, underscores, dots (no spaces, no shell chars)
  return /^[a-zA-Z0-9._-]+$/.test(name) && name.length <= 100;
}

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

// Parse CLI flags
function parseFlags() {
  const args = process.argv.slice(2);
  const flags = {
    help: args.includes('--help') || args.includes('-h'),
    quick: args.includes('--quick'),
    standard: args.includes('--standard'),
    power: args.includes('--power'),
    projectName: args.find(arg => !arg.startsWith('-'))
  };

  // Validate: only one tier flag allowed
  const tierFlags = [flags.quick, flags.standard, flags.power].filter(Boolean);
  if (tierFlags.length > 1) {
    console.error('Error: Only one tier flag allowed (--quick, --standard, or --power)');
    process.exit(1);
  }

  return flags;
}

function showHelp() {
  console.log(`
Usage: npx create-dld <project-name> [options]

Options:
  --quick      🏃 Quick tier (2 min) - No MCP, basic skills only
  --standard   ⭐ Standard tier (5 min) - Context7 + Exa MCP [recommended]
  --power      ⚡ Power tier (15 min) - All MCP servers
  --help, -h   Show this help message

Examples:
  npx create-dld my-project           # Interactive setup
  npx create-dld my-project --quick   # Fast setup, no MCP
  npx create-dld my-project --standard # Recommended setup
  npx create-dld my-project --power   # Full setup

Learn more: https://github.com/Ellevated/dld
`);
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
    console.log('\nPower tier servers require API keys.');
    console.log('Run ./scripts/setup-mcp.sh --tier 3 to complete Power setup.');
  }

  console.log('\nMCP setup complete. Restart Claude Code to activate.');
}

async function main() {
  const flags = parseFlags();

  if (flags.help) {
    showHelp();
    process.exit(0);
  }

  const projectName = flags.projectName;

  if (!projectName) {
    console.log('Usage: npx create-dld <project-name> [options]');
    console.log('Run with --help for all options');
    process.exit(1);
  }

  if (!isValidProjectName(projectName)) {
    console.error('Error: Invalid project name. Use only letters, numbers, hyphens, underscores, and dots.');
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

    // Move template to project (using safe Node.js API)
    cpSync(join(tempDir, TEMPLATE_DIR), projectName, { recursive: true });

    // Initialize git (projectName validated above)
    execSync('git init', { cwd: projectName, stdio: 'pipe' });

    // Cleanup (using safe Node.js API)
    rmSync(tempDir, { recursive: true, force: true });

    console.log(`\nProject created: ${projectName}`);

    // Determine tier (flag or interactive)
    let mcpTier;

    if (flags.quick) {
      mcpTier = 0;
      console.log('\n🏃 Quick tier selected (no MCP)');
    } else if (flags.standard) {
      mcpTier = 1;
      console.log('\n⭐ Standard tier selected (Context7 + Exa)');
    } else if (flags.power) {
      mcpTier = 2;
      console.log('\n⚡ Power tier selected (all MCP)');
    } else {
      // Interactive mode (existing behavior)
      const response = await prompts({
        type: 'select',
        name: 'mcpTier',
        message: 'Configure MCP servers?',
        choices: [
          { title: '⭐ Standard (Recommended)', description: 'Context7 + Exa, 5 min setup', value: 1 },
          { title: '🏃 Quick', description: 'No MCP, 2 min setup', value: 0 },
          { title: '⚡ Power', description: 'All MCP servers, 15 min setup', value: 2 }
        ],
        initial: 0
      });

      // Handle Ctrl+C
      if (response.mcpTier === undefined) {
        console.log('\nSetup cancelled. Project created without MCP.');
        mcpTier = 0;
      } else {
        mcpTier = response.mcpTier;
      }
    }

    await setupMcp(mcpTier);

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
      rmSync(tempDir, { recursive: true, force: true });
      rmSync(projectName, { recursive: true, force: true });
    } catch {}
    process.exit(1);
  }
}

main();
