import * as https from "https";
import * as http from "http";
import { getConfig } from "./config";

interface ScanResult {
  id: string;
  issues: ScanIssue[];
}

export interface ScanIssue {
  filePath: string;
  lineNumber: number;
  issueType: string;
  provider: string;
  currentModel: string;
  recommendedModel: string;
  estimatedMonthlyCost: number;
  estimatedMonthlySavings: number;
  confidence: number;
  description: string;
}

interface ApiResponse<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<ApiResponse<T>> {
  const config = getConfig();
  const url = new URL(path, config.serverUrl);
  const isHttps = url.protocol === "https:";
  const mod = isHttps ? https : http;

  return new Promise((resolve) => {
    const options: https.RequestOptions = {
      hostname: url.hostname,
      port: url.port || (isHttps ? 443 : 80),
      path: url.pathname + url.search,
      method,
      headers: {
        Authorization: `Bearer ${config.apiKey}`,
        "Content-Type": "application/json",
        "User-Agent": "Inferency-VSCode/0.1.0",
      },
    };

    const req = mod.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            resolve({ ok: true, data: JSON.parse(data) });
          } else {
            resolve({
              ok: false,
              error: `HTTP ${res.statusCode}: ${data.substring(0, 200)}`,
            });
          }
        } catch {
          resolve({ ok: false, error: `Invalid JSON response` });
        }
      });
    });

    req.on("error", (err) => {
      resolve({ ok: false, error: err.message });
    });

    if (body) {
      req.write(JSON.stringify(body));
    }
    req.end();
  });
}

export async function scanFiles(
  files: { path: string; content: string }[]
): Promise<ApiResponse<ScanResult>> {
  return request<ScanResult>("POST", "/api/mcp/scan", { files });
}

export async function getRecommendations(): Promise<
  ApiResponse<ScanIssue[]>
> {
  return request<ScanIssue[]>("GET", "/api/recommendations");
}

export async function getPricing(): Promise<
  ApiResponse<{ model: string; provider: string; inputPricePer1k: number; outputPricePer1k: number }[]>
> {
  return request("GET", "/api/pricing/models");
}

export async function checkHealth(): Promise<ApiResponse<{ status: string }>> {
  return request("GET", "/health");
}
