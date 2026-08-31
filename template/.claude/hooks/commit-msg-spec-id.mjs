#!/usr/bin/env node
// Аудит отказов оркестратора 30.08.2026, причина 1 — «гейт слеп».
//
// Автопилот делает работу, коммитит её субъектом без spec-id, гейт реализации
// смотрит на origin/develop, ни одного коммита со своим ID не находит и ставит
// спеке `blocked`. Работа сделана, ветка запушена, а спека выглядит проваленной
// — и так в 9 даунстримах из 15. Раскатка правил в промпты чинит это ровно до
// первого агента, который правило не прочитал; хук чинит структурно.
//
// Правило: пока в окружении стоит непустой CLAUDE_CURRENT_SPEC_PATH (его
// выставляет run-agent.sh на каждый диспатч), subject коммита обязан объявлять
// spec-id в форме, которую УМЕЕТ ЧИТАТЬ гейт. Человек, коммитящий руками, этой
// переменной не имеет и хука не замечает.
//
// Wired by .git-hooks/commit-msg when core.hooksPath is set:
//   git config core.hooksPath .git-hooks
//
// Bypass: DLD_SPEC_SUBJECT_UNCHECKED=1 (последнее средство оператора).
//
// Exit codes:
//   0 — проверять нечего, subject объявляет spec-id, или байпас
//   1 — subject не объявляет spec-id текущей спеки
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';

// Держится в паре с scripts/vps/gate_logic.py:_SPEC_ID_RE. Корпус субъектов в
// test/fixtures/commit-subject-corpus.json прогоняется через ОБЕ реализации —
// расхождение падает тестом, а не тихой спекой в blocked.
const SPEC_ID_RE = /(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*/i;
const SPEC_ID_FULL_RE = /^(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*$/i;

/**
 * Порт scripts/vps/gate_logic.py:match_subject на JS — байт в байт те же формы.
 *
 * @param {string} subject первая строка сообщения коммита
 * @param {string} specId идентификатор спеки, например "TECH-189"
 * @returns {boolean} true, если subject объявляет реализацию specId
 */
export function matchSubject(subject, specId) {
    if (!subject || !specId) return false;

    // Conventional: <type>(<scope>)[!]: <description>
    const conv = /^[a-z]+\(([^)]*)\)!?:/.exec(subject);
    if (conv) {
        const scopes = conv[1].split(',').map((s) => s.trim());
        if (scopes.some((s) => s.toUpperCase() === specId.toUpperCase())) return true;
    }

    // Merge commit: `merge[:] [branch] ['][prefix/]SPEC-ID`
    const escaped = specId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (new RegExp(`^merge[:\\s]\\s*(?:branch\\s+)?['"]?(?:\\S+/)?${escaped}\\b`, 'i').test(subject)) {
        return true;
    }

    // Хвостовые скобки: `... (SPEC-ID)` / `... (SPEC-A, SPEC-B)`. Каждый элемент
    // обязан БЫТЬ id-шаблоном — `(see SPEC-ID)` остаётся отвергнутым.
    const tailMatch = /\(([^()]*)\)\s*$/.exec(subject);
    if (tailMatch) {
        const tail = tailMatch[1].split(',').map((s) => s.trim());
        if (
            tail.every((s) => SPEC_ID_FULL_RE.test(s)) &&
            tail.some((s) => s.toUpperCase() === specId.toUpperCase())
        ) {
            return true;
        }
    }

    // Legacy: `SPEC-ID: <description>`
    if (new RegExp(`^${escaped}:\\s`).test(subject)) return true;

    return false;
}

/**
 * Достать spec-id из пути к спеке (`ai/features/TECH-189-2026-08-30-slug.md`).
 *
 * @param {string} specPath значение CLAUDE_CURRENT_SPEC_PATH
 * @returns {string|null} id или null, если путь не о спеке (инбокс-файл, glob)
 */
export function specIdFromPath(specPath) {
    const m = SPEC_ID_RE.exec(basename(specPath || ''));
    return m ? m[0].toUpperCase() : null;
}

/**
 * Первая содержательная строка сообщения коммита.
 *
 * Комментарии git (`#`) и пустые строки сверху отбрасываются — иначе subject
 * шаблона `git commit` без -m читался бы как решётка.
 *
 * @param {string} raw содержимое файла сообщения
 * @returns {string} subject
 */
export function extractSubject(raw) {
    for (const line of raw.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        return trimmed;
    }
    return '';
}

function main() {
    const messagePath = process.argv[2];
    if (!messagePath) process.exit(0);

    const specPath = process.env.CLAUDE_CURRENT_SPEC_PATH;
    if (!specPath || !specPath.trim()) process.exit(0);

    if (process.env.DLD_SPEC_SUBJECT_UNCHECKED === '1') process.exit(0);

    const specId = specIdFromPath(specPath);
    if (!specId) process.exit(0);

    let raw;
    try {
        raw = readFileSync(messagePath, 'utf-8');
    } catch {
        process.exit(0);
    }

    const subject = extractSubject(raw);

    // `git commit --fixup/--squash` — subject задаёт git, переписывать его нельзя;
    // при rebase --autosquash он схлопнется в исходный коммит, который проверен.
    if (/^(fixup|squash|amend)!/.test(subject)) process.exit(0);

    if (matchSubject(subject, specId)) process.exit(0);

    console.error('');
    console.error('✗ commit-msg-spec-id: subject не объявляет спеку, которую вы выполняете.');
    console.error(`  Спека:   ${specId}   (CLAUDE_CURRENT_SPEC_PATH=${specPath})`);
    console.error(`  Subject: ${subject || '<пусто>'}`);
    console.error('');
    console.error('  Гейт реализации ищет коммит по subject и НИЧЕГО не читает в теле.');
    console.error('  Коммит без id в subject = спека уйдёт в blocked при сделанной работе.');
    console.error('');
    console.error('  Годные формы:');
    console.error(`    feat(${specId}): краткое описание`);
    console.error(`    fix(${specId})!: ломающая правка`);
    console.error(`    fix: краткое описание (${specId})`);
    console.error(`    merge feature/${specId}: ...`);
    console.error('');
    console.error('  Последнее средство: DLD_SPEC_SUBJECT_UNCHECKED=1 git commit ...');
    process.exit(1);
}

// Импорт из тестов не должен запускать проверку.
if (process.argv[1] && basename(process.argv[1]) === 'commit-msg-spec-id.mjs') {
    main();
}
