import * as vscode from "vscode";

const OPTIMIZATION_SUGGESTIONS: Record<
  string,
  { model: string; savings: string; note: string }[]
> = {
  "gpt-4": [
    {
      model: "gpt-4o",
      savings: "~92%",
      note: "Similar quality, significantly cheaper",
    },
    {
      model: "gpt-4o-mini",
      savings: "~99%",
      note: "Best for simple tasks (classification, extraction)",
    },
  ],
  "gpt-4-turbo": [
    {
      model: "gpt-4o",
      savings: "~75%",
      note: "Newer model, better price-performance",
    },
    {
      model: "gpt-4o-mini",
      savings: "~98%",
      note: "For simple tasks only",
    },
  ],
  "claude-3-opus": [
    {
      model: "claude-3-5-sonnet",
      savings: "~80%",
      note: "Comparable quality for most tasks",
    },
    {
      model: "claude-3-haiku",
      savings: "~98%",
      note: "For simple tasks only",
    },
  ],
  "claude-3-sonnet": [
    {
      model: "claude-3-haiku",
      savings: "~92%",
      note: "Good for summarization, extraction",
    },
  ],
  "gemini-1.5-pro": [
    {
      model: "gemini-1.5-flash",
      savings: "~97%",
      note: "Fast and cheap, good for simple tasks",
    },
  ],
};

export class InferencyCodeActionProvider
  implements vscode.CodeActionProvider
{
  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range
  ): vscode.CodeAction[] | undefined {
    const line = document.lineAt(range.start.line);
    const text = line.text;

    // Check if line contains a model reference
    const modelMatch = text.match(/model\s*[:=]\s*["']([^"']+)["']/);
    if (!modelMatch) {
      return undefined;
    }

    const currentModel = modelMatch[1];
    const baseModel = currentModel.split("-20")[0]; // Strip date suffix
    const suggestions = OPTIMIZATION_SUGGESTIONS[baseModel];
    if (!suggestions) {
      return undefined;
    }

    const actions: vscode.CodeAction[] = [];

    for (const suggestion of suggestions) {
      const action = new vscode.CodeAction(
        `Inferency: Switch to ${suggestion.model} (save ${suggestion.savings}) - ${suggestion.note}`,
        vscode.CodeActionKind.QuickFix
      );

      const edit = new vscode.WorkspaceEdit();
      const modelStart = text.indexOf(currentModel);
      if (modelStart >= 0) {
        const startPos = new vscode.Position(range.start.line, modelStart);
        const endPos = new vscode.Position(
          range.start.line,
          modelStart + currentModel.length
        );
        edit.replace(document.uri, new vscode.Range(startPos, endPos), suggestion.model);
      }

      action.edit = edit;
      action.isPreferred = suggestions.indexOf(suggestion) === 0;
      actions.push(action);
    }

    return actions;
  }
}
