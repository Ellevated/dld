# Contributing to DLD

Thank you for your interest in contributing to DLD!

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/Ellevated/dld/issues) to avoid duplicates
2. Use the [bug report template](https://github.com/Ellevated/dld/issues/new?template=bug-report.md)
3. Include steps to reproduce, expected and actual behavior

### Suggesting Features

1. Check [existing issues](https://github.com/Ellevated/dld/issues) for similar requests
2. Use the [feature request template](https://github.com/Ellevated/dld/issues/new?template=feature-request.md)
3. Describe the problem and your proposed solution

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Run tests if available
5. Commit with clear messages
6. Push and open a PR

### Code Style

- Follow existing code patterns in the project
- Keep commits atomic and well-described
- Update documentation if needed

## DLD-Specific Contributions

### Template vs Root (.claude/)

DLD has TWO copies of `.claude/` configuration:

```
template/.claude/   ← Universal template (for all DLD users)
.claude/            ← DLD project-specific (template + customizations)
```

**When modifying `.claude/` files:**

| Change Type | Where to Edit | Then |
|-------------|---------------|------|
| Universal improvement | `template/.claude/` first | Cherry-pick to `.claude/` |
| DLD-specific | `.claude/` only | Document in `.claude/CUSTOMIZATIONS.md` |

**Check divergence:** Run `./scripts/check-sync.sh`

**Details:** See `.claude/CUSTOMIZATIONS.md` for full sync policy.

### Adding Examples

Place new examples in `examples/` directory following the existing structure.

### Translations

- Template translations go in `template/` with appropriate language markers
- Documentation translations should mirror the original structure

## Questions?

- Open a [Discussion](https://github.com/Ellevated/dld/discussions)
- Use the [question template](https://github.com/Ellevated/dld/issues/new?template=question.md)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
