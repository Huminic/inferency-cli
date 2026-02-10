# Inferency

**AI cost optimization for developers.** Scan your codebase for AI API calls, see what they cost, and get recommendations to cut spending by 40-70%.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## What It Does

Inferency scans your code for AI API calls (OpenAI, Anthropic, Google AI) and tells you:

- **Which models you're using** and where
- **How much each call costs** (per 1K invocations)
- **Cheaper alternatives** that maintain quality (e.g., GPT-4 -> GPT-4o saves ~92%)

```
$ inferency scan .

Scanning: /home/user/my-project
Found 14 source files

                  AI API Calls Found: 5
┏━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ File             ┃ Line ┃ Provider  ┃ Model         ┃ Cost/1K     ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ app.py           │   23 │ openai    │ gpt-4         │ $27.00      │
│ app.py           │   45 │ openai    │ gpt-4         │ $27.00      │
│ summarizer.py    │   12 │ anthropic │ claude-3-opus │ $22.50      │
│ classifier.ts    │   31 │ openai    │ gpt-4o-mini   │ $0.20       │
│ embeddings.js    │   18 │ openai    │               │ -           │
└──────────────────┴──────┴───────────┴───────────────┴─────────────┘

Summary:
  openai: 4 call(s)
  anthropic: 1 call(s)

Estimated total cost per 1K calls: $76.70
```

## Quick Start

### 1. Install

```bash
pip install inferency
```

### 2. Get an API Key

Sign up at [inferency.ai](https://inferency.ai) and create an API key in the dashboard.

### 3. Configure

```bash
inferency config YOUR_API_KEY --server-url https://inferency.ai
```

### 4. Scan

```bash
inferency scan .
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `inferency scan <path>` | Scan a directory or file for AI API calls |
| `inferency report <path>` | Generate an optimization report with recommendations |
| `inferency monitor` | Real-time cost monitoring dashboard |
| `inferency config` | Configure API key and server URL |
| `inferency status` | Check connection to Inferency server |
| `inferency pricing` | Show current AI model pricing |

### Scan Options

```bash
inferency scan .                    # Scan current directory
inferency scan ./src                # Scan specific directory
inferency scan app.py               # Scan single file
inferency scan . --json-output      # Output as JSON
inferency scan . --remote           # Submit to Inferency server for analysis
```

### Report Formats

```bash
inferency report .                  # Rich terminal output
inferency report . --format json    # JSON output
inferency report . --format markdown -o report.md   # Save as markdown
```

## Supported Providers

| Provider | SDK Patterns Detected |
|----------|----------------------|
| **OpenAI** | `client.chat.completions.create()`, `ChatCompletion.create()` |
| **Anthropic** | `client.messages.create()`, `Anthropic().messages` |
| **Google AI** | `generateContent()`, `GoogleGenerativeAI`, `getGenerativeModel()` |

## Supported Languages

- Python (`.py`)
- JavaScript (`.js`, `.mjs`, `.cjs`, `.jsx`)
- TypeScript (`.ts`, `.tsx`)

When [tree-sitter](https://tree-sitter.github.io/tree-sitter/) is installed, detection uses AST parsing for higher accuracy. Otherwise, falls back to regex-based detection.

```bash
# Optional: install tree-sitter for AST-based detection
pip install inferency[tree-sitter]
```

## SDK Interceptor (V2)

Automatically capture every LLM API call in your application with zero code changes to your business logic.

### Python

```bash
pip install inferency[interceptor]
```

```python
from inferency.interceptor import init

# Call once at app startup — patches OpenAI and Anthropic SDKs automatically
init(api_key="inf_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")

# All subsequent OpenAI/Anthropic calls are now tracked
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-4o", messages=[...])
# ^ Automatically captured and sent to your Inferency dashboard
```

Options: `server_url`, `sample_rate` (0.0-1.0), `privacy_mode` (redacts prompts), `batch_size`, `flush_interval`.

### Node.js / TypeScript

```bash
npm install @inferency/interceptor
```

```typescript
import { init } from '@inferency/interceptor';

// Call once at app startup
init({ apiKey: 'inf_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' });

// All subsequent OpenAI/Anthropic SDK calls are tracked
import OpenAI from 'openai';
const client = new OpenAI();
const response = await client.chat.completions.create({ model: 'gpt-4o', messages: [...] });
// ^ Automatically captured
```

Options: `serverUrl`, `sampleRate`, `privacyMode`, `batchSize`, `flushInterval`.

### How It Works

The interceptor monkey-patches SDK methods (`client.chat.completions.create`, `client.messages.create`) to record:
- Model, provider, token counts, latency, status code
- Optional: customer ID, project ID, custom tags

Data is batched (50 items or 100ms, whichever comes first) and sent to your Inferency dashboard. The interceptor never modifies LLM responses and all errors are silently caught — your application is never affected.

## VS Code / Cursor Extension

> **Status:** Preview — works with the Inferency server, available in this repo under `extensions/vscode/`.

The VS Code extension provides:

- **Inline cost annotations** — see estimated cost next to every AI API call
- **Quick Fix code actions** — one-click model switch suggestions (e.g., "Switch to gpt-4o, save ~92%")
- **Status bar** — connection status and quick access to dashboard
- **Workspace scanning** — scan all files via Command Palette

### Install from Source

```bash
cd extensions/vscode
npm install
npm run compile
npx @vscode/vsce package
# Install the generated .vsix file in VS Code
```

### Configure

1. Open VS Code Settings
2. Search for "Inferency"
3. Set your API key (`inf_live_...`)
4. Server URL defaults to `https://inferency.ai`

## Examples

The `examples/` directory contains sample projects showing what Inferency detects:

- [`examples/python/`](examples/python/) — OpenAI and Anthropic SDK usage in Python
- [`examples/javascript/`](examples/javascript/) — OpenAI calls in Node.js
- [`examples/typescript/`](examples/typescript/) — Multi-provider TypeScript project

Try scanning them:

```bash
inferency scan examples/python
inferency report examples/typescript --format markdown
```

## How Pricing Works

Cost estimates are based on published provider pricing (per 1M tokens). The scanner assumes average usage of ~500 input tokens and ~200 output tokens per call to estimate cost per 1,000 invocations.

| Model | Input (per 1M) | Output (per 1M) | Est. Cost/1K Calls |
|-------|---------------|-----------------|-------------------|
| gpt-4 | $30.00 | $60.00 | $27.00 |
| gpt-4o | $2.50 | $10.00 | $3.25 |
| gpt-4o-mini | $0.15 | $0.60 | $0.20 |
| claude-3-opus | $15.00 | $75.00 | $22.50 |
| claude-3.5-sonnet | $3.00 | $15.00 | $4.50 |
| claude-3-haiku | $0.25 | $1.25 | $0.38 |
| gemini-1.5-pro | $3.50 | $10.50 | $3.85 |
| gemini-1.5-flash | $0.075 | $0.30 | $0.10 |

## Configuration

The CLI stores configuration at `~/.inferency/config`:

```
api_key=inf_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
server_url=https://inferency.ai
```

You can also use environment variables:

```bash
export INFERENCY_API_KEY=inf_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export INFERENCY_SERVER_URL=https://inferency.ai
```

Environment variables take precedence over the config file.

## Development

```bash
# Clone the repo
git clone https://github.com/Huminic/inferency-cli.git
cd inferency-cli/cli

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run the CLI
inferency --version
```

## License

MIT — see [LICENSE](LICENSE) for details.
