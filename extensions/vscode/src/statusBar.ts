import * as vscode from "vscode";
import { checkHealth } from "./client";
import { isConfigured } from "./config";

let statusBarItem: vscode.StatusBarItem;
let updateInterval: ReturnType<typeof setInterval> | undefined;

export function createStatusBar(context: vscode.ExtensionContext): void {
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  statusBarItem.command = "inferency.showDashboard";
  context.subscriptions.push(statusBarItem);

  updateStatusBar();
  updateInterval = setInterval(updateStatusBar, 30000); // Update every 30s
  context.subscriptions.push({
    dispose: () => {
      if (updateInterval) {
        clearInterval(updateInterval);
      }
    },
  });
}

async function updateStatusBar(): Promise<void> {
  if (!isConfigured()) {
    statusBarItem.text = "$(key) Inferency: Set API Key";
    statusBarItem.tooltip = "Click to configure Inferency API key";
    statusBarItem.command = "inferency.setApiKey";
    statusBarItem.show();
    return;
  }

  statusBarItem.text = "$(pulse) Inferency";
  statusBarItem.tooltip = "Checking connection...";
  statusBarItem.show();

  const result = await checkHealth();
  if (result.ok) {
    statusBarItem.text = "$(check) Inferency: Connected";
    statusBarItem.tooltip = "Connected to Inferency. Click to open dashboard.";
    statusBarItem.command = "inferency.showDashboard";
  } else {
    statusBarItem.text = "$(warning) Inferency: Offline";
    statusBarItem.tooltip = `Connection failed: ${result.error}`;
    statusBarItem.command = "inferency.showDashboard";
  }
}

export function disposeStatusBar(): void {
  if (updateInterval) {
    clearInterval(updateInterval);
  }
  statusBarItem?.dispose();
}
