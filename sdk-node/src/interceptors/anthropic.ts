import { CapturedRequest, ResolvedConfig } from '../types';
import { BatchTransport } from '../transport';

/**
 * Monkey-patches the Anthropic SDK (v0.6+) so that every call to
 * `messages.create()` is transparently intercepted, measured, and
 * reported to the Inferency backend.
 *
 * Design invariants:
 *   1. The original return value (or stream) is NEVER modified.
 *   2. If interception code throws, the error is swallowed and the
 *      original SDK behaviour is preserved.
 *   3. Streaming responses are handled by wrapping the async iterator
 *      to accumulate usage data from stream events.
 */
export function patchAnthropic(
  transport: BatchTransport,
  config: ResolvedConfig,
): boolean {
  try {
    // Attempt to load the Anthropic module. It is a peer dependency
    // and may not be installed in the host application.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const AnthropicModule = require('@anthropic-ai/sdk');
    const AnthropicClass = AnthropicModule.default || AnthropicModule;

    if (!AnthropicClass || !AnthropicClass.prototype) {
      debugLog(config, 'Anthropic class not found or has no prototype');
      return false;
    }

    const OriginalConstructor = AnthropicClass;
    const patchedSymbol = Symbol.for('inferency_patched_anthropic');

    // Intercept new Anthropic(...) calls via Proxy
    const handler: ProxyHandler<any> = {
      construct(target: any, args: any[], newTarget: any) {
        const instance = Reflect.construct(target, args, newTarget);
        try {
          patchInstance(instance, transport, config, patchedSymbol);
        } catch (err) {
          debugLog(config, 'Failed to patch Anthropic instance', err);
        }
        return instance;
      },
    };

    const ProxiedClass = new Proxy(OriginalConstructor, handler);

    // Replace in module cache
    if (AnthropicModule.default) {
      AnthropicModule.default = ProxiedClass;
    }
    try {
      const moduleCache =
        require.cache[require.resolve('@anthropic-ai/sdk')];
      if (moduleCache) {
        if (moduleCache.exports.default) {
          moduleCache.exports.default = ProxiedClass;
        }
        if (typeof moduleCache.exports === 'function') {
          moduleCache.exports = ProxiedClass;
        }
        // Named export
        if (moduleCache.exports.Anthropic) {
          moduleCache.exports.Anthropic = ProxiedClass;
        }
      }
    } catch {
      // Non-critical
    }

    debugLog(config, 'Anthropic SDK patched successfully');
    return true;
  } catch (err) {
    debugLog(config, 'Anthropic SDK not available, skipping patch', err);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Instance-level patching
// ---------------------------------------------------------------------------

function patchInstance(
  instance: any,
  transport: BatchTransport,
  config: ResolvedConfig,
  patchedSymbol: symbol,
): void {
  if (instance[patchedSymbol]) return;
  instance[patchedSymbol] = true;

  // Anthropic SDK v0.6+ exposes client.messages.create()
  const messages = instance.messages;
  if (!messages || typeof messages.create !== 'function') {
    debugLog(config, 'messages.create not found on Anthropic instance');
    return;
  }

  const originalCreate = messages.create.bind(messages);

  messages.create = async function interceptedCreate(
    ...args: any[]
  ): Promise<any> {
    // Sampling gate
    if (config.sampleRate < 1 && Math.random() > config.sampleRate) {
      return originalCreate(...args);
    }

    const startTime = Date.now();
    const requestId = generateRequestId();
    const params = args[0] || {};
    const isStreaming = !!params.stream;

    try {
      const result = await originalCreate(...args);

      if (isStreaming) {
        return wrapStream(result, {
          transport,
          config,
          requestId,
          model: params.model || 'unknown',
          startTime,
        });
      }

      // Non-streaming: result is a Message object
      // Anthropic response shape:
      //   { id, type, role, content, model, stop_reason, usage: { input_tokens, output_tokens } }
      try {
        const latencyMs = Date.now() - startTime;
        const captured: CapturedRequest = {
          request_id: requestId,
          provider: 'anthropic',
          model: result.model || params.model || 'unknown',
          prompt_tokens: result.usage?.input_tokens,
          completion_tokens: result.usage?.output_tokens,
          latency_ms: latencyMs,
          status_code: 200,
          tags: { ...config.tags },
          timestamp: new Date(startTime).toISOString(),
        };
        transport.enqueue(captured);
      } catch (captureErr) {
        debugLog(config, 'Error capturing Anthropic response', captureErr);
      }

      return result;
    } catch (err: any) {
      // The LLM call itself failed. Capture what we can.
      try {
        const latencyMs = Date.now() - startTime;
        const captured: CapturedRequest = {
          request_id: requestId,
          provider: 'anthropic',
          model: params.model || 'unknown',
          latency_ms: latencyMs,
          status_code: err?.status || err?.statusCode || 0,
          tags: { ...config.tags },
          timestamp: new Date(startTime).toISOString(),
          metadata: { error: err?.message },
        };
        transport.enqueue(captured);
      } catch (captureErr) {
        debugLog(
          config,
          'Error capturing Anthropic error response',
          captureErr,
        );
      }

      throw err;
    }
  };
}

// ---------------------------------------------------------------------------
// Stream wrapping
// ---------------------------------------------------------------------------

interface StreamContext {
  transport: BatchTransport;
  config: ResolvedConfig;
  requestId: string;
  model: string;
  startTime: number;
}

/**
 * Wraps an Anthropic streaming response to accumulate usage data.
 *
 * Anthropic streaming emits events like:
 *   - message_start (includes initial usage.input_tokens)
 *   - content_block_delta
 *   - message_delta (includes usage.output_tokens)
 *   - message_stop
 *
 * We intercept the async iterator to read these events without
 * modifying the data the caller receives.
 */
function wrapStream(stream: any, ctx: StreamContext): any {
  if (!stream || typeof stream[Symbol.asyncIterator] !== 'function') {
    return stream;
  }

  const originalIterator = stream[Symbol.asyncIterator].bind(stream);
  let inputTokens: number | undefined;
  let outputTokens: number | undefined;
  let resolvedModel: string = ctx.model;

  stream[Symbol.asyncIterator] = function () {
    const inner = originalIterator();
    return {
      async next(): Promise<IteratorResult<any>> {
        try {
          const result = await inner.next();

          if (result.done) {
            // Stream ended - emit captured request
            try {
              const latencyMs = Date.now() - ctx.startTime;
              const captured: CapturedRequest = {
                request_id: ctx.requestId,
                provider: 'anthropic',
                model: resolvedModel,
                prompt_tokens: inputTokens,
                completion_tokens: outputTokens,
                latency_ms: latencyMs,
                status_code: 200,
                tags: { ...ctx.config.tags },
                timestamp: new Date(ctx.startTime).toISOString(),
              };
              ctx.transport.enqueue(captured);
            } catch (captureErr) {
              debugLog(
                ctx.config,
                'Error capturing streamed Anthropic response',
                captureErr,
              );
            }
            return result;
          }

          // Accumulate usage from stream events
          const event = result.value;
          if (event) {
            // message_start event contains the message with usage
            if (event.type === 'message_start' && event.message) {
              if (event.message.model) resolvedModel = event.message.model;
              if (event.message.usage) {
                inputTokens = event.message.usage.input_tokens ?? inputTokens;
              }
            }

            // message_delta event contains output token count
            if (event.type === 'message_delta' && event.usage) {
              outputTokens = event.usage.output_tokens ?? outputTokens;
            }
          }

          return result;
        } catch (err) {
          // Stream error
          try {
            const latencyMs = Date.now() - ctx.startTime;
            const captured: CapturedRequest = {
              request_id: ctx.requestId,
              provider: 'anthropic',
              model: resolvedModel,
              latency_ms: latencyMs,
              status_code: 0,
              tags: { ...ctx.config.tags },
              timestamp: new Date(ctx.startTime).toISOString(),
              metadata: {
                error: (err as any)?.message || 'Stream error',
              },
            };
            ctx.transport.enqueue(captured);
          } catch {
            // Silently drop capture errors
          }
          throw err;
        }
      },
      async return(value?: any): Promise<IteratorResult<any>> {
        if (inner.return) return inner.return(value);
        return { done: true, value: undefined };
      },
      async throw(err?: any): Promise<IteratorResult<any>> {
        if (inner.throw) return inner.throw(err);
        throw err;
      },
    };
  };

  return stream;
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function generateRequestId(): string {
  try {
    return require('crypto').randomUUID();
  } catch {
    try {
      return require('uuid').v4();
    } catch {
      return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    }
  }
}

function debugLog(
  config: ResolvedConfig,
  message: string,
  error?: unknown,
): void {
  if (!config.debug) return;
  if (error) {
    console.debug(`[@inferency/interceptor:anthropic] ${message}:`, error);
  } else {
    console.debug(`[@inferency/interceptor:anthropic] ${message}`);
  }
}
