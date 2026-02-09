import * as vscode from "vscode";

export interface InferencyConfig {
  apiKey: string;
  serverUrl: string;
  enableInlineAnnotations: boolean;
  enableStatusBar: boolean;
}

export function getConfig(): InferencyConfig {
  const config = vscode.workspace.getConfiguration("inferency");
  return {
    apiKey: config.get<string>("apiKey", ""),
    serverUrl: config.get<string>("serverUrl", "https://inferency.ai"),
    enableInlineAnnotations: config.get<boolean>(
      "enableInlineAnnotations",
      true
    ),
    enableStatusBar: config.get<boolean>("enableStatusBar", true),
  };
}

export function isConfigured(): boolean {
  const config = getConfig();
  return config.apiKey.startsWith("inf_live_") && config.apiKey.length > 20;
}
