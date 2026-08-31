/**
 * Tests for .claude/hooks/commit-msg-spec-id.mjs
 *
 * Аудит отказов оркестратора 30.08.2026, причина 1: автопилот коммитил subject
 * без spec-id, гейт реализации такой коммит не видел и ставил спеке `blocked`
 * при сделанной работе — 9 даунстримов из 15.
 *
 * Проверяется:
 * - корпус субъектов из test/fixtures/commit-subject-corpus.json (та же таблица
 *   гоняется через Python-гейт в tests/unit/test_commit_subject_corpus.py —
 *   расхождение реализаций падает тестом, а не тихой спекой);
 * - хук молчит без CLAUDE_CURRENT_SPEC_PATH (ручной коммит человека);
 * - хук молчит на inbox-пути без id и на fixup!/squash!;
 * - байпас DLD_SPEC_SUBJECT_UNCHECKED=1;
 * - реальный запуск процессом: exit 0 / exit 1 и текст отказа.
 */

import { execFileSync } from 'child_process';
import { writeFileSync, mkdirSync, rmSync, readFileSync } from 'fs';
import { join } from 'path';
import { strict as assert } from 'assert';

const HOOK_PATH = join(process.cwd(), '.claude/hooks/commit-msg-spec-id.mjs');
const TEMPLATE_HOOK_PATH = join(process.cwd(), 'template/.claude/hooks/commit-msg-spec-id.mjs');
const CORPUS_PATH = join(process.cwd(), 'test/fixtures/commit-subject-corpus.json');
const TEST_DIR = join(process.cwd(), 'test/scripts/.tmp-commit-msg');

const corpus = JSON.parse(readFileSync(CORPUS_PATH, 'utf-8'));
const { matchSubject, specIdFromPath, extractSubject } = await import(
    `file://${HOOK_PATH.replace(/\\/g, '/')}`
);

function setup() {
    mkdirSync(TEST_DIR, { recursive: true });
}

function cleanup() {
    try { rmSync(TEST_DIR, { recursive: true, force: true }); } catch {}
}

/** Запустить хук как процесс на заданном subject. */
function runHook(subject, env = {}) {
    const msgFile = join(TEST_DIR, 'COMMIT_EDITMSG');
    writeFileSync(msgFile, subject, 'utf-8');
    try {
        execFileSync('node', [HOOK_PATH, msgFile], {
            encoding: 'utf-8',
            timeout: 15_000,
            // stderr в pipe, иначе отказ хука печатается посреди отчёта тестов
            // и выглядит как падение прогона.
            stdio: ['pipe', 'pipe', 'pipe'],
            env: { ...process.env, CLAUDE_CURRENT_SPEC_PATH: '', DLD_SPEC_SUBJECT_UNCHECKED: '', ...env },
        });
        return { exitCode: 0, stderr: '' };
    } catch (err) {
        return { exitCode: err.status || 1, stderr: (err.stderr || '').toString() };
    }
}

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

// --- корпус: обе реализации обязаны читать одинаково ------------------------

test('корпус: принятые формы проходят matchSubject', () => {
    for (const subject of corpus.accepted) {
        assert.equal(
            matchSubject(subject, corpus.spec_id),
            true,
            `должно приниматься: ${JSON.stringify(subject)}`,
        );
    }
});

test('корпус: отвергнутые формы не проходят matchSubject', () => {
    for (const subject of corpus.rejected) {
        assert.equal(
            matchSubject(subject, corpus.spec_id),
            false,
            `должно отвергаться: ${JSON.stringify(subject)}`,
        );
    }
});

// --- извлечение id и subject ------------------------------------------------

test('specIdFromPath достаёт id из пути к спеке', () => {
    assert.equal(specIdFromPath('ai/features/TECH-189-2026-08-30-slug.md'), 'TECH-189');
    assert.equal(specIdFromPath('ai/features/growth-042-x.md'), 'GROWTH-042');
    assert.equal(specIdFromPath('ai/inbox/2026-08-30-idea.md'), null);
    assert.equal(specIdFromPath(''), null);
});

test('extractSubject пропускает комментарии и пустые строки', () => {
    assert.equal(extractSubject('\n# комментарий git\n\nfeat(TECH-189): x\n'), 'feat(TECH-189): x');
    assert.equal(extractSubject('# только комментарий\n'), '');
});

// --- поведение процесса -----------------------------------------------------

test('без CLAUDE_CURRENT_SPEC_PATH хук молчит', () => {
    const r = runHook('chore: ручной коммит человека');
    assert.equal(r.exitCode, 0);
});

test('пустой CLAUDE_CURRENT_SPEC_PATH хук молчит', () => {
    const r = runHook('chore: уборка', { CLAUDE_CURRENT_SPEC_PATH: '   ' });
    assert.equal(r.exitCode, 0);
});

test('subject без spec-id при активной спеке отвергается', () => {
    const r = runHook('chore: уборка', {
        CLAUDE_CURRENT_SPEC_PATH: 'ai/features/TECH-189-2026-08-30-slug.md',
    });
    assert.equal(r.exitCode, 1);
    assert.ok(r.stderr.includes('TECH-189'), 'в отказе назван id спеки');
    assert.ok(r.stderr.includes('feat(TECH-189):'), 'в отказе показана годная форма');
});

test('subject со spec-id при активной спеке проходит', () => {
    const r = runHook('feat(TECH-189): гейт', {
        CLAUDE_CURRENT_SPEC_PATH: 'ai/features/TECH-189-2026-08-30-slug.md',
    });
    assert.equal(r.exitCode, 0);
});

test('inbox-путь без id проверять нечем — хук молчит', () => {
    const r = runHook('chore: разобрать инбокс', {
        CLAUDE_CURRENT_SPEC_PATH: 'ai/inbox/2026-08-30-idea.md',
    });
    assert.equal(r.exitCode, 0);
});

test('fixup! не проверяется — subject задаёт git', () => {
    const r = runHook('fixup! feat(TECH-189): гейт', {
        CLAUDE_CURRENT_SPEC_PATH: 'ai/features/TECH-189-2026-08-30-slug.md',
    });
    assert.equal(r.exitCode, 0);
});

test('байпас DLD_SPEC_SUBJECT_UNCHECKED=1 пропускает', () => {
    const r = runHook('chore: уборка', {
        CLAUDE_CURRENT_SPEC_PATH: 'ai/features/TECH-189-2026-08-30-slug.md',
        DLD_SPEC_SUBJECT_UNCHECKED: '1',
    });
    assert.equal(r.exitCode, 0);
});

test('две ветки дерева несут один и тот же хук', () => {
    assert.equal(
        readFileSync(HOOK_PATH, 'utf-8'),
        readFileSync(TEMPLATE_HOOK_PATH, 'utf-8'),
        '.claude/ и template/.claude/ разошлись — правка доехала в одно дерево',
    );
});

// --- runner -----------------------------------------------------------------

setup();
let failed = 0;
for (const [name, fn] of tests) {
    try {
        fn();
        console.log(`  ✓ ${name}`);
    } catch (err) {
        failed += 1;
        console.error(`  ✗ ${name}`);
        console.error(`    ${err.message}`);
    }
}
cleanup();

console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed === 0 ? 0 : 1);
