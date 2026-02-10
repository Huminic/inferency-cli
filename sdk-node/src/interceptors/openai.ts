import { CapturedRequest, ResolvedConfig } from '../types';
import { BatchTransport } from '../transport';

/**
 * Monkey-patches the OpenAI SDK (v4+) so that every call to
 * `chat.completions.create()` is transparently intercepted,
 * measured, and reported to the Inferency backend.
 *
 * Design invariants:
 *   1. The original return value (or stream) is NEVER modified.
 *   2. If interception code throws, the error is swallowed and the
 *      original SDK behaviour is preserved.
 *   3. Streaming responses are handled by wrapping the async iterator
 *      to accumulate usage data from stream chunks.
 */
export function patchOpenAI(
  transport: BatchTransport,
  config: ResolvedConfig,
): boolean {
  try {
    // Attempt to load the OpenAI module. It is a peer dependency and may not
    // be installed in the host application.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const OpenAIModule = require('openai');
    const OpenAIClass = OpenAIModule.default || OpenAIModule;

    if (!OpenAIClass || !OpenAIClass.prototype) {
      debugLog(config, 'OpenAI class not found or has no prototype');
      return false;
    }

    // We need to patch the Completions resource which is accessed via
    // client.chat.completions. The resource classes are instantiated lazily
    // by the SDK, so we patch the Chat.Completions.create method on the
    // prototype of the Completions class.
    //
    // In openai v4 the structure is:
    //   OpenAI -> .chat (Chat) -> .completions (Completions) -> .create()
    //
    // The Completions class is exported at OpenAI.Chat.Completions (or
    // the internal module path). We can also patch at the instance level
    // by intercepting the getter.

    // Strategy: Wrap the OpenAI constructor to patch instances after creation.
    const OriginalConstructor = OpenAIClass;
    const patchedSymbol = Symbol.for('inferency_patched');

    // Intercept new OpenAI(...) calls
    const handler: ProxyHandler<any> = {
      construct(target: any, args: any[], newTarget: any) {
        const instance = Reflect.construct(target, args, newTarget);
        try {
          patchInstance(instance, transport, config, patchedSymbol);
        } catch (err) {
          debugLog(config, 'Failed to patch OpenAI instance', err);
        }
        return instance;
      },
    };

    const ProxiedClass = new Proxy(OriginalConstructor, handler);

    // Replace the default export so that `new OpenAI()` goes through our proxy
    if (OpenAIModule.default) {
      OpenAIModule.default = ProxiedClass;
    }
    // Also replace the module itself if it's the constructor
    try {
      const moduleCache = require.cache[require.resolve('openai')];
      if (moduleCache) {
        if (moduleCache.exports.default) {
          moduleCache.exports.default = ProxiedClass;
        }
        if (typeof moduleCache.exports === 'function') {
          moduleCache.exports = ProxiedClass;
        }
        // OpenAI v4 uses named export OpenAI as well
        if (moduleCache.exports.OpenAI) {
          moduleCache.exports.OpenAI = ProxiedClass;
        }
      }
    } catch {
      // Non-critical: the Proxy-based approach will still work for
      // imports that happen after init().
    }

    debugLog(config, 'OpenAI SDK patched successfully');
    return true;
  } catch (err) {
    // Module not installed or other load error - that's fine.
    debugLog(config, 'OpenAI SDK not available, skipping patch', err);
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
  // Guard against double-patching
  if (instance[patchedSymbol]) return;
  instance[patchedSymbol] = true;

  // chat.completions is a getter that returns a Completions resource instance.
  // We need to patch the .create() method on that resource.
  const completions = instance.chat?.completions;
  if (!completions || typeof completions.create !== 'function') {
    debugLog(config, 'chat.completions.create not found on instance');
    return;
  }

  const originalCreate = completions.create.bind(completions);

  completions.create = async function interceptedCreate(
    ...args: any[]
  ): Promise<any> {
    // Determine whether we should sample this request
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

      // Non-streaming: result is a ChatCompletion object
      try {
        const latencyMs = Date.now() - startTime;
        const captured: CapturedRequest = {
          request_id: requestId,
          provider: 'openai',
          model: result.model || params.model || 'unknown',
          prompt_tokens: result.usage?.prompt_tokens,
          completion_tokens: result.usage?.completion_tokens,
          latency_ms: latencyMs,
          status_code: 200,
          tags: { ...config.tags },
          timestamp: new Date(startTime).toISOString(),
        };
        transport.enqueue(captured);
      } catch (captureErr) {
        debugLog(config, 'Error capturing OpenAI response', captureErr);
      }

      return result;
    } catch (err: any) {
      // The LLM call itself failed. Still capture what we can.
      try {
        const latencyMs = Date.now() - startTime;
        const captured: CapturedRequest = {
          request_id: requestId,
          provider: 'openai',
          model: params.model || 'unknown',
          latency_ms: latencyMs,
          status_code: err?.status || err?.statusCode || 0,
          tags: { ...config.tags },
          timestamp: new Date(startTime).toISOString(),
          metadata: { error: err?.message },
        };
        transport.enqueue(captured);
      } catch (captureErr) {
        debugLog(config, 'Error capturing OpenAI error response', captureErr);
      }

      // Re-throw the original error so the host app sees it unchanged
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
 * Wraps an OpenAI streaming response so we can accumulate usage data
 * from the stream chunks without altering the data the caller receives.
 *
 * OpenAI v4 streams implement Symbol.asyncIterator. We wrap that iterator
 * to intercept each chunk and then emit a CapturedRequest once the stream
 * ends.
 */
function wrapStream(stream: any, ctx: StreamContext): any {
  // If the stream doesn't support async iteration, return it unchanged.
  if (!stream || typeof stream[Symbol.asyncIterator] !== 'function') {
    return stream;
  }

  const originalIterator = stream[Symbol.asyncIterator].bind(stream);
  let promptTokens: number | undefined;
  let completionTokens: number | undefined;
  let resolvedModel: string = ctx.model;

  stream[Symbol.asyncIterator] = function* wrappedIterator() {
    // We can't use a generator with async iteration directly,
    // so we return an async iterator object.
  } as any;

  // Replace with proper async iterator
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
                provider: 'openai',
                model: resolvedModel,
                prompt_tokens: promptTokens,
                completion_tokens: completionTokens,
                latency_ms: latencyMs,
                status_code: 200,
                tags: { ...ctx.config.tags },
                timestamp: new Date(ctx.startTime).toISOString(),
              };
              ctx.transport.enqueue(captured);
            } catch (captureErr) {
              debugLog(
                ctx.config,
                'Error capturing streamed OpenAI response',
                captureErr,
              );
            }
            return result;
          }

          // Accumulate usage from chunks
          const chunk = result.value;
          if (chunk) {
            if (chunk.model) resolvedModel = chunk.model;

            // OpenAI streams may include usage in the final chunk
            // (when stream_options: { include_usage: true } is set)
            if (chunk.usage) {
              promptTokens = chunk.usage.prompt_tokens ?? promptTokens;
              completionTokens =
                chunk.usage.completion_tokens ?? completionTokens;
            }
          }

          return result;
        } catch (err) {
          // Stream error - still try to capture
          try {
            const latencyMs = Date.now() - ctx.startTime;
            const captured: CapturedRequest = {
              request_id: ctx.requestId,
              provider: 'openai',
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
    // Node 16+ has crypto.randomUUID
    return require('crypto').randomUUID();
  } catch {
    // Fallback to uuid package
    try {
      return require('uuid').v4();
    } catch {
      // Last resort: timestamp + random
      return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    }
  }
}

function debugLog(config: ResolvedConfig, message: string, error?: unknown): void {
  if (!config.debug) return;
  if (error) {
    console.debug(`[@inferency/interceptor:openai] ${message}:`, error);
  } else {
    console.debug(`[@inferency/interceptor:openai] ${message}`);
  }
}
