import { CapturedRequest, ResolvedConfig } from './types';

/**
 * BatchTransport accumulates CapturedRequest items and sends them
 * to the Inferency backend in batches. It flushes when:
 *   - The batch reaches config.batchSize (default 50), OR
 *   - config.flushIntervalMs (default 100ms) has elapsed since the first
 *     un-flushed item was enqueued.
 *
 * All network errors are caught and logged (debug mode) or silently dropped.
 * The transport never throws, never blocks, and never modifies the caller's
 * control flow.
 */
export class BatchTransport {
  private buffer: CapturedRequest[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private config: ResolvedConfig;
  private fetchFn: typeof globalThis.fetch;
  private shuttingDown = false;

  constructor(config: ResolvedConfig) {
    this.config = config;

    // Use native fetch (Node 18+) or fall back to node-fetch
    if (typeof globalThis.fetch === 'function') {
      this.fetchFn = globalThis.fetch.bind(globalThis);
    } else {
      try {
        // eslint-disable-next-line @typescript-eslint/no-var-requires
        const nodeFetch = require('node-fetch');
        this.fetchFn = nodeFetch.default || nodeFetch;
      } catch {
        // If neither is available, use a no-op that warns once
        let warned = false;
        this.fetchFn = (async () => {
          if (!warned) {
            warned = true;
            console.warn(
              '[@inferency/interceptor] No fetch implementation available. ' +
                'Install node-fetch or use Node 18+ for telemetry.',
            );
          }
          return new Response(null, { status: 0 });
        }) as unknown as typeof globalThis.fetch;
      }
    }
  }

  /**
   * Enqueue a captured request for batched delivery.
   * This method never throws.
   */
  enqueue(request: CapturedRequest): void {
    if (this.shuttingDown) return;

    try {
      this.buffer.push(request);

      if (this.buffer.length >= this.config.batchSize) {
        this.flush();
      } else if (!this.timer) {
        this.timer = setTimeout(() => {
          this.timer = null;
          this.flush();
        }, this.config.flushIntervalMs);
      }
    } catch (err) {
      this.debugLog('Error enqueuing request', err);
    }
  }

  /**
   * Flush the current buffer to the backend.
   * Errors are caught and logged; data is dropped if the server is unreachable.
   */
  flush(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    if (this.buffer.length === 0) return;

    const batch = this.buffer.splice(0);
    this.sendBatch(batch);
  }

  /**
   * Graceful shutdown: flush remaining buffer and stop accepting new items.
   * Returns a promise that resolves once the final batch has been sent
   * (or the send attempt has completed / timed out).
   */
  async shutdown(): Promise<void> {
    this.shuttingDown = true;

    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    if (this.buffer.length > 0) {
      const batch = this.buffer.splice(0);
      await this.sendBatch(batch);
    }
  }

  // ------------------------------------------------------------------ private

  private async sendBatch(batch: CapturedRequest[]): Promise<void> {
    const url = `${this.config.serverUrl}/api/v1/ingest/batch`;

    try {
      const response = await this.fetchFn(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.config.apiKey}`,
          'User-Agent': '@inferency/interceptor 0.1.0',
        },
        body: JSON.stringify({ events: batch }),
        // Abort after 5 seconds so we never block the host app
        signal: AbortSignal.timeout ? AbortSignal.timeout(5000) : undefined,
      });

      if (!response.ok) {
        this.debugLog(
          `Batch send failed: HTTP ${response.status} ${response.statusText}`,
        );
      } else {
        this.debugLog(`Batch sent successfully: ${batch.length} events`);
      }
    } catch (err) {
      // Network error, server down, timeout, etc.
      // Drop the batch silently (or with debug log). Never block the caller.
      this.debugLog('Batch send error (data dropped)', err);
    }
  }

  private debugLog(message: string, error?: unknown): void {
    if (!this.config.debug) return;
    if (error) {
      console.debug(`[@inferency/interceptor] ${message}:`, error);
    } else {
      console.debug(`[@inferency/interceptor] ${message}`);
    }
  }
}
