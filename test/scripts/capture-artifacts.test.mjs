/**
 * Tests for .claude/scripts/lib/capture-artifacts.mjs
 *
 * The case that matters: /spark commits every spec and lifecycle record it
 * writes. A capture that reads only `git status` sees none of it — the first
 * version of this function reported `artifacts: 1` for a run that had just
 * produced nine specs, because the one file it found was an uncommitted counter.
 */

import { execFileSync } from 'child_process';
import { mkdirSync, writeFileSync, rmSync, existsSync, mkdtempSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { strict as assert } from 'assert';
import { captureArtifacts } from '../../.claude/scripts/lib/capture-artifacts.mjs';

const TMP = join(process.cwd(), 'test/scripts/.tmp-capture');
const REPO = join(TMP, 'repo');
const DEST = join(TMP, 'out');

function git(args, cwd = REPO) {
  return execFileSync('git', args, { cwd, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
}

function setup() {
  cleanup();
  mkdirSync(REPO, { recursive: true });
  git(['init', '-q'], REPO);
  git(['config', 'user.email', 'test@example.com']);
  git(['config', 'user.name', 'test']);
  writeFileSync(join(REPO, 'seed.txt'), 'seed\n');
  git(['add', '-A']);
  git(['commit', '-q', '-m', 'base']);
}

function cleanup() {
  try { rmSync(TMP, { recursive: true, force: true }); } catch { /* best effort */ }
}

function testCapturesCommittedWork() {
  const base = git(['rev-parse', 'HEAD']);

  // What a skill does: write a spec and commit it.
  mkdirSync(join(REPO, 'ai/features'), { recursive: true });
  writeFileSync(join(REPO, 'ai/features/FTR-001.md'), '# spec\n');
  git(['add', '-A']);
  git(['commit', '-q', '-m', 'docs: create spec FTR-001']);

  // git status is empty here — that is the whole point.
  assert.equal(git(['status', '--porcelain']), '', 'precondition: tree is clean after commit');

  const { captured } = captureArtifacts(REPO, join(DEST, 'committed'), base);
  assert.ok(
    captured.includes('ai/features/FTR-001.md'),
    `committed spec must be captured, got ${JSON.stringify(captured)}`
  );
  assert.ok(existsSync(join(DEST, 'committed/ai/features/FTR-001.md')), 'file must be copied to dest');
  console.log('  PASS: testCapturesCommittedWork');
}

function testCapturesUncommittedWork() {
  const base = git(['rev-parse', 'HEAD']);
  writeFileSync(join(REPO, 'loose.txt'), 'not committed\n');

  const { captured } = captureArtifacts(REPO, join(DEST, 'loose'), base);
  assert.ok(captured.includes('loose.txt'), `uncommitted file must be captured, got ${JSON.stringify(captured)}`);
  console.log('  PASS: testCapturesUncommittedWork');
}

function testCapturesBothAtOnce() {
  const base = git(['rev-parse', 'HEAD']);

  writeFileSync(join(REPO, 'ai/features/FTR-002.md'), '# spec 2\n');
  git(['add', '-A']);
  git(['commit', '-q', '-m', 'docs: create spec FTR-002']);
  writeFileSync(join(REPO, 'counter.txt'), '1\n');

  const { captured } = captureArtifacts(REPO, join(DEST, 'both'), base);
  assert.ok(captured.includes('ai/features/FTR-002.md'), 'committed half');
  assert.ok(captured.includes('counter.txt'), 'uncommitted half');
  console.log('  PASS: testCapturesBothAtOnce');
}

function testNoBaseRefStillCapturesWorkingTree() {
  writeFileSync(join(REPO, 'orphan.txt'), 'x\n');
  const { captured } = captureArtifacts(REPO, join(DEST, 'nobase'), null);
  assert.ok(captured.includes('orphan.txt'), 'working tree capture must not depend on a base ref');
  console.log('  PASS: testNoBaseRefStillCapturesWorkingTree');
}

function testNonRepoIsReportedNotThrown() {
  // Must live outside this repository: a directory under D:\dev\dld is still
  // inside a git work tree, so `git status` there succeeds and the case never
  // arises. The first version of this test made exactly that mistake.
  const plain = mkdtempSync(join(tmpdir(), 'capture-nonrepo-'));
  try {
    const res = captureArtifacts(plain, join(DEST, 'plain'), null);
    assert.deepEqual(res.captured, [], 'nothing captured outside a repo');
    assert.ok(res.note, 'must explain why, rather than failing the run');
  } finally {
    try { rmSync(plain, { recursive: true, force: true }); } catch { /* best effort */ }
  }
  console.log('  PASS: testNonRepoIsReportedNotThrown');
}

function main() {
  console.log('capture-artifacts.test.mjs');
  setup();
  try {
    testCapturesCommittedWork();
    testCapturesUncommittedWork();
    testCapturesBothAtOnce();
    testNoBaseRefStillCapturesWorkingTree();
    testNonRepoIsReportedNotThrown();
    console.log('\n5/5 tests passed');
  } finally {
    cleanup();
  }
}

main();
