# Contributing to Inferency

Thanks for your interest in contributing to Inferency.

## Getting Started

### CLI (Python)

```bash
cd cli
pip install -e ".[dev]"
pytest
```

### VS Code Extension

```bash
cd extensions/vscode
npm install
npm run compile
```

## Project Structure

```
inferency-cli/
  cli/                      # Python CLI (pip install inferency)
    inferency/
      cli.py                # Main entry point + top-level commands
      client.py             # HTTP client for Inferency server
      commands/
        scan.py             # inferency scan
        report.py           # inferency report
        monitor.py          # inferency monitor
      parsers/
        detector.py         # AI API call detection (regex + tree-sitter)
    pyproject.toml
  extensions/
    vscode/                 # VS Code / Cursor extension
      src/
        extension.ts        # Extension entry point
        client.ts           # HTTP client for Inferency server
        annotations.ts      # Inline cost annotations
        codeActions.ts      # Quick Fix model switch suggestions
        statusBar.ts        # Status bar integration
        config.ts           # Extension configuration
      package.json
      tsconfig.json
  examples/                 # Sample projects for testing
    python/
    javascript/
    typescript/
```

## Adding a New Provider

To add detection for a new AI provider:

1. Add regex patterns to `cli/inferency/parsers/detector.py` in `REGEX_PATTERNS`
2. Add model pricing to `MODEL_COSTS` in the same file
3. Add optimization suggestions to `cli/inferency/commands/report.py` in `OPTIMIZATION_MAP`
4. Mirror the patterns in `extensions/vscode/src/annotations.ts`
5. Add an example file in `examples/`

## Adding a New CLI Command

1. Create `cli/inferency/commands/your_command.py`
2. Register in `cli/inferency/cli.py` with `main.add_command(your_command)`

## Guidelines

- Keep dependencies minimal
- Support Python 3.8+
- Use type hints
- Test with `pytest`
- Follow existing code style

## Reporting Issues

Open an issue at [github.com/Huminic/inferency-cli/issues](https://github.com/Huminic/inferency-cli/issues).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
