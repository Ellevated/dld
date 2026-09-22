/**
 * Tests for .claude/scripts/lib/agent-includes.mjs
 *
 * The defect: Claude Code does not expand `@path` lines inside agent files, so
 * `_shared/output-conventions.md` reached 5 of 782 production subagent runs. The fix
 * writes the shared text into each agent between generated markers. What must hold:
 * a raw line is expanded, a second pass changes nothing, an edited source makes the
 * block stale, the two procedure modules are removed rather than expanded, and the
 * file's line endings survive.
 */

import { mkdirSync, writeFileSync, rmSync } from 'fs';
import { join } from 'path';
import { strict as assert } from 'assert';
import { expandText, beginMarker, NOT_INLINED } from '../../.claude/scripts/lib/agent-includes.mjs';

const TMP = join(process.cwd(), 'test/scripts/.tmp-agent-includes');
const SHARED = join(TMP, '_shared');

function setup() {
  cleanup();
  mkdirSync(SHARED, { recursive: true });
  writeFileSync(join(SHARED, 'rule.md'), '# Rule\nWrite numbers as words.\n');
  writeFileSync(join(SHARED, 'context-loader.md'), '# Loader\nRead everything first.\n');
}

function cleanup() {
  try { rmSync(TMP, { recursive: true, force: true }); } catch { /* best effort */ }
}

const AGENT = '---\nname: a\n---\n\nIntro.\n\n@.claude/agents/_shared/rule.md\n\nOutro.\n';

function testRawLineIsExpanded() {
  const res = expandText(AGENT, SHARED);
  assert.deepEqual(res.raw, ['rule.md']);
  assert.ok(res.changed);
  assert.ok(!res.text.includes('@.claude/agents/_shared/rule.md'), 'raw line must be gone');
  assert.ok(res.text.includes(beginMarker('rule.md')));
  assert.ok(res.text.includes('Write numbers as words.'));
  assert.ok(res.text.includes('<!-- /include: _shared/rule.md -->'));
  assert.ok(res.text.startsWith('---\nname: a\n---\n\nIntro.\n'), 'frontmatter untouched');
  console.log('  PASS: testRawLineIsExpanded');
}

function testSecondPassIsANoOp() {
  const once = expandText(AGENT, SHARED).text;
  const twice = expandText(once, SHARED);
  assert.equal(twice.changed, false);
  assert.deepEqual(twice.raw, []);
  assert.deepEqual(twice.stale, []);
  console.log('  PASS: testSecondPassIsANoOp');
}

function testEditedSourceMakesTheBlockStale() {
  const once = expandText(AGENT, SHARED).text;
  writeFileSync(join(SHARED, 'rule.md'), '# Rule\nWrite numbers as words, always.\n');
  try {
    const res = expandText(once, SHARED);
    assert.deepEqual(res.stale, ['rule.md']);
    assert.ok(res.text.includes('Write numbers as words, always.'));
    assert.ok(!res.text.includes('Write numbers as words.\n'), 'old body replaced, not appended');
  } finally {
    writeFileSync(join(SHARED, 'rule.md'), '# Rule\nWrite numbers as words.\n');
  }
  console.log('  PASS: testEditedSourceMakesTheBlockStale');
}

function testHandEditedBlockIsStale() {
  const once = expandText(AGENT, SHARED).text;
  const tampered = once.replace('Write numbers as words.', 'Write numbers as digits.');
  const res = expandText(tampered, SHARED);
  assert.deepEqual(res.stale, ['rule.md'], 'an edit inside the block must not survive');
  assert.ok(res.text.includes('Write numbers as words.'));
  console.log('  PASS: testHandEditedBlockIsStale');
}

function testProcedureModulesAreRemovedNotExpanded() {
  assert.ok(NOT_INLINED.has('context-loader.md'));
  const agent = 'Step 0.\n\n@.claude/agents/_shared/context-loader.md\n\n**Before any code:** read.\n';
  const res = expandText(agent, SHARED);
  assert.deepEqual(res.dropped, ['context-loader.md']);
  assert.ok(!res.text.includes('Read everything first.'), 'must not be inlined');
  assert.ok(!res.text.includes('@.claude'), 'raw line removed');
  assert.equal(res.text, 'Step 0.\n\n**Before any code:** read.\n', 'no double blank line left');
  console.log('  PASS: testProcedureModulesAreRemovedNotExpanded');
}

function testCrlfIsPreserved() {
  const crlf = AGENT.replace(/\n/g, '\r\n');
  const res = expandText(crlf, SHARED);
  assert.ok(!/[^\r]\n/.test(res.text), 'every newline stays CRLF');
  assert.equal(expandText(res.text, SHARED).changed, false, 'CRLF output is stable too');
  console.log('  PASS: testCrlfIsPreserved');
}

function testProseMentionIsNotAnInclude() {
  const prose = 'Text.\n@_shared/rule.md is explicit that inventing a URL is wrong.\n';
  const res = expandText(prose, SHARED);
  assert.equal(res.changed, false);
  console.log('  PASS: testProseMentionIsNotAnInclude');
}

function testMissingModuleThrows() {
  assert.throws(() => expandText('@.claude/agents/_shared/nope.md\n', SHARED), /not found/);
  console.log('  PASS: testMissingModuleThrows');
}

function main() {
  console.log('agent-includes.test.mjs');
  setup();
  try {
    testRawLineIsExpanded();
    testSecondPassIsANoOp();
    testEditedSourceMakesTheBlockStale();
    testHandEditedBlockIsStale();
    testProcedureModulesAreRemovedNotExpanded();
    testCrlfIsPreserved();
    testProseMentionIsNotAnInclude();
    testMissingModuleThrows();
    console.log('\n8/8 tests passed');
  } finally {
    cleanup();
  }
}

main();
