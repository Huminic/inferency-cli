import * as vscode from "vscode";
import { getConfig, isConfigured } from "./config";
import { scanFiles } from "./client";
import {
  updateAnnotations,
  getLocalAnnotations,
  decorationType,
} from "./annotations";
import { InferencyCodeActionProvider } from "./codeActions";
import { createStatusBar } from "./statusBar";

let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel("Inferency");
  outputChannel.appendLine("Inferency extension activated");

  // Status bar
  const config = getConfig();
  if (config.enableStatusBar) {
    createStatusBar(context);
  }

  // Code actions (model switch suggestions)
  const codeActionProvider = new InferencyCodeActionProvider();
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      [
        { scheme: "file", language: "typescript" },
        { scheme: "file", language: "javascript" },
        { scheme: "file", language: "typescriptreact" },
        { scheme: "file", language: "javascriptreact" },
        { scheme: "file", language: "python" },
      ],
      codeActionProvider,
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );

  // Inline annotations on document change
  if (config.enableInlineAnnotations) {
    const updateEditor = (editor: vscode.TextEditor | undefined) => {
      if (!editor) {
        return;
      }
      const decorations = getLocalAnnotations(editor.document);
      editor.setDecorations(decorationType, decorations);
    };

    // Update on active editor change
    context.subscriptions.push(
      vscode.window.onDidChangeActiveTextEditor(updateEditor)
    );

    // Update on document change
    context.subscriptions.push(
      vscode.workspace.onDidChangeTextDocument((e) => {
        const editor = vscode.window.activeTextEditor;
        if (editor && e.document === editor.document) {
          updateEditor(editor);
        }
      })
    );

    // Initial update
    if (vscode.window.activeTextEditor) {
      updateEditor(vscode.window.activeTextEditor);
    }
  }

  // Commands
  context.subscriptions.push(
    vscode.commands.registerCommand("inferency.scanFile", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("No active file to scan.");
        return;
      }

      if (!isConfigured()) {
        const action = await vscode.window.showWarningMessage(
          "Inferency API key not configured.",
          "Set API Key"
        );
        if (action === "Set API Key") {
          vscode.commands.executeCommand("inferency.setApiKey");
        }
        return;
      }

      const document = editor.document;
      outputChannel.appendLine(`Scanning: ${document.fileName}`);

      const result = await scanFiles([
        {
          path: document.fileName,
          content: document.getText(),
        },
      ]);

      if (result.ok && result.data) {
        const issues = result.data.issues;
        if (issues.length === 0) {
          vscode.window.showInformationMessage(
            "Inferency: No AI API calls found in this file."
          );
        } else {
          vscode.window.showInformationMessage(
            `Inferency: Found ${issues.length} AI API call(s). Check inline annotations.`
          );
          updateAnnotations(editor, issues);
        }
        outputChannel.appendLine(
          `Scan complete: ${issues.length} findings`
        );
      } else {
        vscode.window.showErrorMessage(
          `Inferency scan failed: ${result.error}`
        );
        outputChannel.appendLine(`Scan failed: ${result.error}`);
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("inferency.scanWorkspace", async () => {
      if (!isConfigured()) {
        const action = await vscode.window.showWarningMessage(
          "Inferency API key not configured.",
          "Set API Key"
        );
        if (action === "Set API Key") {
          vscode.commands.executeCommand("inferency.setApiKey");
        }
        return;
      }

      const workspaceFolders = vscode.workspace.workspaceFolders;
      if (!workspaceFolders) {
        vscode.window.showWarningMessage("No workspace folder open.");
        return;
      }

      const files = await vscode.workspace.findFiles(
        "**/*.{ts,tsx,js,jsx,py}",
        "**/node_modules/**",
        100
      );

      if (files.length === 0) {
        vscode.window.showInformationMessage(
          "No source files found in workspace."
        );
        return;
      }

      outputChannel.appendLine(
        `Scanning workspace: ${files.length} files`
      );

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "Inferency: Scanning workspace...",
          cancellable: false,
        },
        async (progress) => {
          const fileContents: { path: string; content: string }[] = [];

          for (let i = 0; i < files.length; i++) {
            progress.report({
              increment: (100 / files.length),
              message: `${i + 1}/${files.length} files`,
            });

            const doc = await vscode.workspace.openTextDocument(files[i]);
            fileContents.push({
              path: files[i].fsPath,
              content: doc.getText(),
            });
          }

          const result = await scanFiles(fileContents);
          if (result.ok && result.data) {
            const issues = result.data.issues;
            vscode.window.showInformationMessage(
              `Inferency: Scanned ${files.length} files, found ${issues.length} AI API call(s).`
            );
            outputChannel.appendLine(
              `Workspace scan complete: ${issues.length} findings across ${files.length} files`
            );
          } else {
            vscode.window.showErrorMessage(
              `Inferency scan failed: ${result.error}`
            );
          }
        }
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("inferency.showDashboard", () => {
      const config = getConfig();
      vscode.env.openExternal(
        vscode.Uri.parse(`${config.serverUrl}/dashboard`)
      );
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("inferency.setApiKey", async () => {
      const key = await vscode.window.showInputBox({
        prompt: "Enter your Inferency API key",
        placeHolder: "inf_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        password: true,
        validateInput: (value) => {
          if (!value.startsWith("inf_live_")) {
            return 'API key must start with "inf_live_"';
          }
          if (value.length < 20) {
            return "API key is too short";
          }
          return null;
        },
      });

      if (key) {
        await vscode.workspace
          .getConfiguration("inferency")
          .update("apiKey", key, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage(
          "Inferency API key saved."
        );
      }
    })
  );

  // Watch for config changes
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("inferency")) {
        outputChannel.appendLine("Configuration changed");
      }
    })
  );

  outputChannel.appendLine("Inferency extension ready");
}

export function deactivate(): void {
  outputChannel?.appendLine("Inferency extension deactivated");
}
