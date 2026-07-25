# Output Conventions (all agents)

Calibration for Claude Opus 5 / Sonnet 5 defaults. These models write longer,
narrate more, and delegate more eagerly than the models this framework was built for.

## Length

Match the length of what you write — both chat replies and files on disk — to what the
task needs. Cover the substance; do not pad with filler sections, redundant summaries,
restated context, or boilerplate. A report that says everything in half the words is a
better report, not a lazier one.

## Scope

Deliver what was asked, at the scope intended. Make routine judgment calls yourself, and
check in only when different readings of the request would lead to materially different
work. If the request seems mistaken or a better approach exists, say so in a sentence and
continue with the task as asked rather than quietly narrowing, widening, or transforming
it. Finish the whole task, and stop short of actions clearly beyond what was asked.

## Verification

You verify your own work; that is expected and needs no instruction. Do not add extra
verification passes, do not re-read your output to "double-check" it, and never spawn a
subagent to review what you just produced. Deterministic gates (hooks, tests, CI) are the
verification layer — trust them instead of duplicating them in prose.

## Delegation

Delegate to a subagent only for large tasks that are genuinely independent and
parallelizable, such as a wide multi-file investigation. Do not delegate work you can
finish yourself in a handful of tool calls. If one subagent can do it, use one rather
than several.

## Corrections

Only correct an earlier statement when the error would change the reader's code,
conclusions, or decisions. State the correction plainly and move on. For slips that
change nothing, fix and continue without narrating it.
