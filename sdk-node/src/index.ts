import { InferencyConfig, ResolvedConfig } from './types';
import { BatchTransport } from './transport';
import { patchOpenAI } from './interceptors/openai';
import { patchAnthropic } from './interceptors/anthropic';

// Re-export public types
export type { InferencyConfig, CapturedRequest } from './types';

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

let transport: BatchTransport | null = null;
let resolvedConfig: ResolvedConfig | null = null;
let initialized = false;

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Initialize the Inferency interceptor.
 *
 * Call this once at application startup, before creating any OpenAI or
 * Anthropic client instances. The function auto-detects which SDKs are
 * installed and patches only those that are available.
 *
 * @example
 * ```typescript
 * import { init } from '@inferency/interceptor';
 *
 * init({
 *   apiKey: process.env.INFERENCY_API_KEY!,
 *   debug: true,
 *   tags: { environment: 'production', service: 'chat-api' },
 * });
 * ```
 */
export function init(config: InferencyConfig): void {
  if (initialized) {
    debugLog('init() called more than once. Ignoring subsequent call.');
    return;
  }

  // Merge user config with defaults
  const merged: ResolvedConfig = {
    apiKey: config.apiKey,
    serverUrl: (config.serverUrl || 'https://inferency.ai').replace(/\/+$/, ''),
    enabled: config.enabled !== false,
    sampleRate: clamp(config.sampleRate ?? 1.0, 0, 1),
    batchSize: config.batchSize ?? 50,
    flushIntervalMs: config.flushIntervalMs ?? 100,
    privacyMode: config.privacyMode ?? false,
    debug: config.debug ?? false,
    tags: { ...(config.tags || {}) },
  };

  resolvedConfig = merged;

  if (!merged.enabled) {
    debugLog('Inferency interceptor disabled via config.');
    initialized = true;
    return;
  }

  if (!merged.apiKey) {
    console.warn(
      '[@inferency/interceptor] No apiKey provided. Interceptor will not send data.',
    );
    initialized = true;
    return;
  }

  // Create the transport layer
  transport = new BatchTransport(merged);

  // Auto-detect and patch installed SDKs
  let patchedAny = false;

  const openaiPatched = patchOpenAI(transport, merged);
  if (openaiPatched) {
    patchedAny = true;
    debugLog('OpenAI SDK interceptor active.');
  }

  const anthropicPatched = patchAnthropic(transport, merged);
  if (anthropicPatched) {
    patchedAny = true;
    debugLog('Anthropic SDK interceptor active.');
  }

  if (!patchedAny) {
    debugLog(
      'No supported LLM SDKs detected. Install openai (>=4.0.0) or ' +
        '@anthropic-ai/sdk (>=0.6.0) as dependencies.',
    );
  }

  initialized = true;
  debugLog(
    `Initialized. Server: ${merged.serverUrl}, Sample rate: ${merged.sampleRate}, ` +
      `Batch size: ${merged.batchSize}, Flush interval: ${merged.flushIntervalMs}ms`,
  );
}

/**
 * Returns true if the interceptor has been initialized and is enabled.
 */
export function isActive(): boolean {
  return initialized && (resolvedConfig?.enabled ?? false) && transport !== null;
}

/**
 * Gracefully shut down the interceptor.
 *
 * Flushes any remaining buffered events to the backend and releases
 * resources. Call this before your process exits (e.g. in a SIGTERM
 * handler or server shutdown hook).
 *
 * @example
 * ```typescript
 * import { shutdown } from '@inferency/interceptor';
 *
 * process.on('SIGTERM', async () => {
 *   await shutdown();
 *   process.exit(0);
 * });
 * ```
 */
export async function shutdown(): Promise<void> {
  if (!initialized) return;

  debugLog('Shutting down...');

  if (transport) {
    await transport.shutdown();
    transport = null;
  }

  initialized = false;
  resolvedConfig = null;

  debugLog('Shutdown complete.');
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function debugLog(message: string): void {
  if (!resolvedConfig?.debug) return;
  console.debug(`[@inferency/interceptor] ${message}`);
}
