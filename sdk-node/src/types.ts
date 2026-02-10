export interface InferencyConfig {
  /** API key for authenticating with the Inferency backend */
  apiKey: string;

  /** Base URL of the Inferency server. Default: https://inferency.ai */
  serverUrl?: string;

  /** Enable or disable interception. Default: true */
  enabled?: boolean;

  /** Sampling rate between 0 and 1. Default: 1.0 (capture all requests) */
  sampleRate?: number;

  /** Maximum number of requests per batch before flushing. Default: 50 */
  batchSize?: number;

  /** Milliseconds to wait before flushing a partial batch. Default: 100 */
  flushIntervalMs?: number;

  /** When true, prompt and completion content is redacted. Default: false */
  privacyMode?: boolean;

  /** Enable debug logging to console. Default: false */
  debug?: boolean;

  /** Key-value tags applied to all captured requests from this instance */
  tags?: Record<string, string>;
}

export interface CapturedRequest {
  /** Unique identifier for this LLM API call */
  request_id: string;

  /** LLM provider: "openai" or "anthropic" */
  provider: string;

  /** Model identifier used for the request (e.g. "gpt-4o", "claude-sonnet-4-20250514") */
  model: string;

  /** Number of tokens in the prompt/input */
  prompt_tokens?: number;

  /** Number of tokens in the completion/output */
  completion_tokens?: number;

  /** Estimated cost in USD for this request */
  cost_usd?: number;

  /** Wall-clock latency of the API call in milliseconds */
  latency_ms?: number;

  /** HTTP status code returned by the provider */
  status_code?: number;

  /** Optional customer identifier for multi-tenant tracking */
  customer_id?: string;

  /** Optional project identifier */
  project_id?: string;

  /** Per-request tags */
  tags?: Record<string, string>;

  /** Arbitrary metadata */
  metadata?: Record<string, any>;

  /** ISO 8601 timestamp of when the request was initiated */
  timestamp?: string;
}

/**
 * Resolved config with all defaults applied.
 * Used internally after init() merges user config with defaults.
 */
export interface ResolvedConfig {
  apiKey: string;
  serverUrl: string;
  enabled: boolean;
  sampleRate: number;
  batchSize: number;
  flushIntervalMs: number;
  privacyMode: boolean;
  debug: boolean;
  tags: Record<string, string>;
}
