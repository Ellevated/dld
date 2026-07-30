#!/usr/bin/env node
/**
 * Phase 0: Codebase Inventory — deterministic file + symbol scan.
 *
 * Layer 1: File inventory (fs + readdir) — 100% coverage guaranteed.
 * Layer 2: Symbol extraction (tree-sitter or regex fallback).
 *
 * Usage: node codebase-inventory.mjs <target_dir>
 * Output: JSON to stdout
 *
 * Optional dependencies (install for enhanced symbol extraction):
 *   npm install tree-sitter tree-sitter-python tree-sitter-typescript
 */

import { statSync, readFileSync, readdirSync, existsSync } from 'fs';
import { join, extname, relative, resolve, basename } from 'path';

// --- Constants ---

const IGNORE_DIRS = new Set([
  'node_modules', '.git', '.next', '__pycache__', '.venv', 'venv',
  'dist', 'build', '.cache', 'coverage', '.nyc_output', '.tox',
  '.eggs', '.mypy_cache', '.pytest_cache', '.ruff_cache', '.turbo',
  '.svelte-kit', '.nuxt', '.output', 'target', 'vendor',
]);

const IGNORE_FILES = new Set([
  '.DS_Store', 'Thumbs.db', '.gitkeep',
  'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'Pipfile.lock',
]);

const BINARY_EXTS = new Set([
  '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.webp', '.bmp',
  '.woff', '.woff2', '.ttf', '.eot', '.otf',
  '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
  '.pdf', '.doc', '.docx', '.xls', '.xlsx',
  '.mp3', '.mp4', '.wav', '.avi', '.mov',
  '.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe',
  '.wasm', '.bin', '.dat', '.db', '.sqlite',
]);

const LANG_MAP = {
  '.py': 'python', '.pyi': 'python',
  '.js': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript', '.jsx': 'javascript',
  '.ts': 'typescript', '.tsx': 'typescript',
  '.go': 'go',
  '.rs': 'rust',
  '.java': 'java',
  '.rb': 'ruby',
  '.php': 'php',
  '.swift': 'swift',
  '.kt': 'kotlin',
  '.cs': 'csharp',
  '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp',
  '.c': 'c', '.h': 'c', '.hpp': 'cpp',
  '.sql': 'sql',
  '.sh': 'shell', '.bash': 'shell', '.zsh': 'shell',
  '.md': 'markdown',
  '.json': 'json',
  '.yaml': 'yaml', '.yml': 'yaml',
  '.toml': 'toml',
  '.html': 'html', '.htm': 'html',
  '.css': 'css', '.scss': 'scss', '.less': 'less',
  '.vue': 'vue', '.svelte': 'svelte',
};

const TEST_PATTERNS = [
  /test[_/]/i, /tests[_/]/i, /spec[_/]/i, /specs[_/]/i,
  /__tests__/i, /\.test\.\w+$/, /\.spec\.\w+$/, /_test\.\w+$/,
  /test_\w+\.py$/, /\w+_test\.go$/,
];

// --- Layer 1: File Walk ---

function walkDir(dir, baseDir) {
  const results = [];
  let entries;
  try { entries = readdirSync(dir, { withFileTypes: true }); }
  catch { return results; }

  for (const entry of entries) {
    if (IGNORE_DIRS.has(entry.name)) continue;
    if (IGNORE_FILES.has(entry.name)) continue;
    const fullPath = join(dir, entry.name);

    if (entry.isDirectory()) {
      results.push(...walkDir(fullPath, baseDir));
    } else if (entry.isFile()) {
      const ext = extname(entry.name);
      if (BINARY_EXTS.has(ext)) continue;
      const relPath = relative(baseDir, fullPath);
      const language = LANG_MAP[ext] || null;
      let loc = 0, lineCount = 0;
      try {
        const content = readFileSync(fullPath, 'utf-8');
        const lines = content.split('\n');
        lineCount = lines.length;
        loc = lines.filter(l => l.trim().length > 0).length;
      } catch { /* skip unreadable files */ }
      const stat = statSync(fullPath);
      results.push({
        path: relPath, language, loc, lines: lineCount, size: stat.size,
        symbols: [], imports: [], exports: [],
      });
    }
  }
  return results;
}

// --- Layer 2a: tree-sitter (opt-in) ---

let tsParser = null;
const loadedGrammars = {};

async function initTreeSitter() {
  try {
    const TS = await import('tree-sitter');
    tsParser = new TS.default();
    return true;
  } catch { return false; }
}

async function loadGrammar(lang) {
  if (loadedGrammars[lang] !== undefined) return loadedGrammars[lang];
  const pkgMap = {
    python: 'tree-sitter-python',
    javascript: 'tree-sitter-javascript',
    typescript: 'tree-sitter-typescript/typescript',
    tsx: 'tree-sitter-typescript/tsx',
  };
  const pkg = pkgMap[lang];
  if (!pkg) { loadedGrammars[lang] = null; return null; }
  try {
    const mod = await import(pkg);
    loadedGrammars[lang] = mod.default;
    return mod.default;
  } catch { loadedGrammars[lang] = null; return null; }
}

function extractSymbolsTS(content, language) {
  const grammar = loadedGrammars[language];
  if (!grammar || !tsParser) return null;
  try {
    tsParser.setLanguage(grammar);
    const tree = tsParser.parse(content);
    const symbols = [];
    const symbolTypes = {
      python: { function_definition: 'function', class_definition: 'class' },
      javascript: { function_declaration: 'function', class_declaration: 'class', method_definition: 'method' },
      typescript: { function_declaration: 'function', class_declaration: 'class', interface_declaration: 'interface', type_alias_declaration: 'type', method_definition: 'method' },
    };
    const types = symbolTypes[language] || {};
    function visit(node) {
      if (types[node.type]) {
        const nameNode = node.childForFieldName('name');
        if (nameNode) {
          symbols.push({
            name: nameNode.text,
            type: types[node.type],
            line: node.startPosition.row + 1,
            end_line: node.endPosition.row + 1,
          });
        }
      }
      for (const child of node.children) visit(child);
    }
    visit(tree.rootNode);
    tree.delete();
    return symbols;
  } catch { return null; }
}

// --- Layer 2b: Regex fallback ---

function extractSymbolsRegex(content, language) {
  const symbols = [];
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;
    if (language === 'python') {
      if ((m = line.match(/^class\s+(\w+)/))) symbols.push({ name: m[1], type: 'class', line: i + 1 });
      else if ((m = line.match(/^(\s*)(?:async\s+)?def\s+(\w+)/))) {
        symbols.push({ name: m[2], type: m[1].length > 0 ? 'method' : 'function', line: i + 1 });
      }
    }
    if (language === 'javascript' || language === 'typescript') {
      if ((m = line.match(/^(?:export\s+)?class\s+(\w+)/))) symbols.push({ name: m[1], type: 'class', line: i + 1 });
      else if ((m = line.match(/^(?:export\s+)?(?:async\s+)?function\s+(\w+)/))) symbols.push({ name: m[1], type: 'function', line: i + 1 });
      else if ((m = line.match(/^\s+(?:async\s+)?(\w+)\s*\(/)) && !line.includes('if') && !line.includes('for')) symbols.push({ name: m[1], type: 'method', line: i + 1 });
      if (language === 'typescript') {
        if ((m = line.match(/^(?:export\s+)?interface\s+(\w+)/))) symbols.push({ name: m[1], type: 'interface', line: i + 1 });
        else if ((m = line.match(/^(?:export\s+)?type\s+(\w+)/))) symbols.push({ name: m[1], type: 'type', line: i + 1 });
      }
    }
    if (language === 'go') {
      if ((m = line.match(/^type\s+(\w+)\s+struct/))) symbols.push({ name: m[1], type: 'struct', line: i + 1 });
      else if ((m = line.match(/^type\s+(\w+)\s+interface/))) symbols.push({ name: m[1], type: 'interface', line: i + 1 });
      else if ((m = line.match(/^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)/))) symbols.push({ name: m[1], type: 'function', line: i + 1 });
    }
  }
  return symbols;
}

// --- Import extraction ---

function extractImports(content, language) {
  const imports = [];
  const lines = content.split('\n');
  for (const line of lines) {
    let m;
    if (language === 'python') {
      if ((m = line.match(/^from\s+([\w.]+)\s+import\s+(.+)/)))
        imports.push({ from: m[1], names: m[2].split(',').map(s => s.trim().split(/\s+as\s+/)[0]) });
      else if ((m = line.match(/^import\s+([\w.]+)/)))
        imports.push({ from: m[1], names: [m[1].split('.').pop()] });
    }
    if (language === 'javascript' || language === 'typescript') {
      if ((m = line.match(/import\s+.*?from\s+['"](.*?)['"]/)))
        imports.push({ from: m[1] });
      else if ((m = line.match(/require\(\s*['"](.*?)['"]\s*\)/)))
        imports.push({ from: m[1] });
    }
    if (language === 'go') {
      if ((m = line.match(/^\s+"([\w./]+)"/)))
        imports.push({ from: m[1] });
    }
  }
  return imports;
}

// --- Export extraction ---

function extractExports(content, language) {
  const exports = [];
  const lines = content.split('\n');
  for (const line of lines) {
    let m;
    if (language === 'python') {
      if ((m = line.match(/__all__\s*=\s*\[(.*?)\]/)))
        exports.push(...m[1].replace(/['"]/g, '').split(',').map(s => s.trim()).filter(Boolean));
    }
    if (language === 'javascript' || language === 'typescript') {
      if ((m = line.match(/^export\s+(?:default\s+)?(?:class|function|const|let|var|interface|type|enum)\s+(\w+)/)))
        exports.push(m[1]);
      else if ((m = line.match(/^export\s+default\s+(\w+)/)))
        exports.push(m[1]);
    }
  }
  return exports;
}

// --- Dependency graph ---

function buildDependencyGraph(files) {
  const graph = {};
  const fileSet = new Set(files.map(f => f.path));
  for (const file of files) {
    const deps = [];
    for (const imp of file.imports) {
      const from = imp.from;
      // Try to resolve relative imports to actual files
      for (const candidate of fileSet) {
        if (candidate.includes(from.replace(/\./g, '/')) || candidate.includes(from)) {
          deps.push(candidate);
        }
      }
    }
    if (deps.length > 0) graph[file.path] = [...new Set(deps)];
  }
  return graph;
}

// --- Stats ---

function computeStats(files) {
  const byDirectory = {};
  for (const f of files) {
    const dir = f.path.includes('/') ? f.path.substring(0, f.path.lastIndexOf('/')) : '.';
    if (!byDirectory[dir]) byDirectory[dir] = { files: 0, loc: 0 };
    byDirectory[dir].files++;
    byDirectory[dir].loc += f.loc;
  }

  const isTestFile = (path) => TEST_PATTERNS.some(p => p.test(path));
  const sourceFiles = files.filter(f => f.language && !isTestFile(f.path) && !['markdown', 'json', 'yaml', 'toml', 'html', 'css', 'scss', 'less'].includes(f.language));
  const testFiles = files.filter(f => isTestFile(f.path));
  const testedPaths = new Set();
  for (const t of testFiles) {
    const name = basename(t.path).replace(/test_|_test|\.test|\.spec/gi, '').replace(extname(t.path), '');
    for (const s of sourceFiles) {
      if (basename(s.path).replace(extname(s.path), '') === name) testedPaths.add(s.path);
    }
  }

  return {
    by_directory: byDirectory,
    largest_files: files.sort((a, b) => b.loc - a.loc).slice(0, 10).map(f => ({ path: f.path, loc: f.loc })),
    no_tests: sourceFiles.filter(f => !testedPaths.has(f.path)).map(f => f.path),
    test_files: testFiles.length,
    source_files: sourceFiles.length,
  };
}

// --- Main ---

async function main() {
  const targetDir = resolve(process.argv[2] || '.');
  if (!existsSync(targetDir)) {
    console.error(`Directory not found: ${targetDir}`);
    process.exit(2);
  }

  // Layer 1: File inventory (100% coverage)
  const files = walkDir(targetDir, targetDir);

  // Layer 2: Symbol extraction
  const hasTreeSitter = await initTreeSitter();
  let tsLanguages = 0;

  for (const file of files) {
    if (!file.language || ['markdown', 'json', 'yaml', 'toml'].includes(file.language)) continue;
    let content;
    try { content = readFileSync(join(targetDir, file.path), 'utf-8'); }
    catch { continue; }

    // Try tree-sitter first, fallback to regex
    if (hasTreeSitter) {
      const grammar = await loadGrammar(file.language);
      if (grammar) {
        const tsSymbols = extractSymbolsTS(content, file.language);
        if (tsSymbols) { file.symbols = tsSymbols; tsLanguages++; }
        else file.symbols = extractSymbolsRegex(content, file.language);
      } else {
        file.symbols = extractSymbolsRegex(content, file.language);
      }
    } else {
      file.symbols = extractSymbolsRegex(content, file.language);
    }

    file.imports = extractImports(content, file.language);
    file.exports = extractExports(content, file.language);
  }

  const dependencies = buildDependencyGraph(files);
  const stats = computeStats(files);

  // Count languages
  const languages = {};
  for (const f of files) {
    if (f.language) languages[f.language] = (languages[f.language] || 0) + 1;
  }

  const inventory = {
    meta: {
      project: basename(targetDir),
      scan_date: new Date().toISOString().split('T')[0],
      total_files: files.length,
      total_loc: files.reduce((sum, f) => sum + f.loc, 0),
      languages,
      extraction_method: hasTreeSitter ? (tsLanguages > 0 ? 'tree-sitter' : 'regex') : 'regex',
    },
    files: files.sort((a, b) => a.path.localeCompare(b.path)),
    dependencies,
    stats,
  };

  console.log(JSON.stringify(inventory, null, 2));
}

main().catch(e => { console.error(e.message); process.exit(2); });
