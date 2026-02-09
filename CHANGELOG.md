# Changelog

## 0.1.0 (2026-02-09)

Initial release.

### CLI
- `inferency scan` — scan directories and files for AI API calls (OpenAI, Anthropic, Google AI)
- `inferency report` — generate optimization reports (text, JSON, markdown)
- `inferency monitor` — real-time cost monitoring dashboard
- `inferency config` — configure API key and server URL
- `inferency status` — check server connection
- `inferency pricing` — display model pricing table
- Regex-based detection with optional Tree-sitter AST parsing
- Supports Python, JavaScript, and TypeScript

### VS Code Extension
- Inline cost annotations on AI API calls
- Quick Fix code actions for model switching
- Status bar with connection indicator
- Workspace and single-file scanning
- API key configuration via settings
