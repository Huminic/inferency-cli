# @inferency/interceptor

Node.js SDK that captures LLM API calls from the OpenAI and Anthropic SDKs and sends telemetry to the Inferency backend.

## Installation

```bash
npm install @inferency/interceptor
```

The package requires at least one of these peer dependencies:

```bash
npm install openai          # v4.0.0+
npm install @anthropic-ai/sdk  # v0.6.0+
```

## Quick Start

Call `init()` once at application startup, **before** creating any LLM client instances:

```typescript
import { init } from '@inferency/interceptor';

init({
  apiKey: process.env.INFERENCY_API_KEY!,
  tags: { environment: 'production', service: 'chat-api' },
});

// Now use OpenAI / Anthropic as normal - calls are automatically captured.
import OpenAI from 'openai';
const openai = new OpenAI();

const response = await openai.chat.completions.create({
  model: 'gpt-4o',
  messages: [{ role: 'user', content: 'Hello' }],
});
```

## Configuration

| Option            | Type                      | Default                 | Description                                      |
|-------------------|---------------------------|-------------------------|--------------------------------------------------|
| `apiKey`          | `string`                  | **(required)**          | Inferency API key                                |
| `serverUrl`       | `string`                  | `https://inferency.ai`  | Inferency backend URL                            |
| `enabled`         | `boolean`                 | `true`                  | Enable/disable interception                      |
| `sampleRate`      | `number`                  | `1.0`                   | Fraction of requests to capture (0-1)            |
| `batchSize`       | `number`                  | `50`                    | Max events per batch before flush                |
| `flushIntervalMs` | `number`                  | `100`                   | Milliseconds before flushing a partial batch     |
| `privacyMode`     | `boolean`                 | `false`                 | Redact prompt/completion content                 |
| `debug`           | `boolean`                 | `false`                 | Log debug info to console                        |
| `tags`            | `Record<string, string>`  | `{}`                    | Tags applied to every captured request           |

## API

### `init(config: InferencyConfig): void`

Initialize the interceptor. Auto-detects installed SDKs and patches only those available.

### `isActive(): boolean`

Returns `true` if the interceptor is initialized, enabled, and has a transport connection.

### `shutdown(): Promise<void>`

Flushes remaining buffered events and releases resources. Call this before process exit.

```typescript
process.on('SIGTERM', async () => {
  await shutdown();
  process.exit(0);
});
```

## Supported SDKs

| Provider   | SDK Package          | Patched Method              |
|------------|----------------------|-----------------------------|
| OpenAI     | `openai` v4+         | `chat.completions.create()` |
| Anthropic  | `@anthropic-ai/sdk` v0.6+ | `messages.create()`    |

Both streaming and non-streaming calls are captured.

## What Gets Captured

Each LLM API call produces a `CapturedRequest` with:

- `request_id` - Unique UUID for the call
- `provider` - `"openai"` or `"anthropic"`
- `model` - Model identifier (e.g. `"gpt-4o"`, `"claude-sonnet-4-20250514"`)
- `prompt_tokens` / `completion_tokens` - Token usage
- `latency_ms` - Wall-clock latency
- `status_code` - HTTP status from the provider
- `tags` - Merged global + per-request tags
- `timestamp` - ISO 8601 timestamp

Prompt and completion **content** is never captured (unless you build a custom extension). When `privacyMode` is enabled, even metadata is minimized.

## Safety Guarantees

1. The interceptor **never modifies** LLM responses.
2. If telemetry fails (network error, server down), data is silently dropped.
3. Interceptor errors are caught internally and **never propagate** to host application code.
4. The original SDK behaviour is preserved in all cases.

## Requirements

- Node.js 16+
- TypeScript 5+ (for development)
