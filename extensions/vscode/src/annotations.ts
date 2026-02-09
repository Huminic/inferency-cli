import * as vscode from "vscode";
import { ScanIssue } from "./client";

const AI_CALL_PATTERNS = [
  // OpenAI
  {
    pattern:
      /(?:openai|client)\.chat\.completions\.create|\.ChatCompletion\.create/g,
    provider: "openai",
  },
  // Anthropic
  {
    pattern: /(?:anthropic|client)\.messages\.create/g,
    provider: "anthropic",
  },
  // Google
  {
    pattern:
      /(?:genai|model)\.generate_?[Cc]ontent|GoogleGenerativeAI|getGenerativeModel/g,
    provider: "google",
  },
];

const MODEL_COSTS: Record<string, { input: number; output: number }> = {
  "gpt-4": { input: 30, output: 60 },
  "gpt-4-turbo": { input: 10, output: 30 },
  "gpt-4o": { input: 2.5, output: 10 },
  "gpt-4o-mini": { input: 0.15, output: 0.6 },
  "gpt-3.5-turbo": { input: 0.5, output: 1.5 },
  "claude-3-opus": { input: 15, output: 75 },
  "claude-3-sonnet": { input: 3, output: 15 },
  "claude-3-5-sonnet": { input: 3, output: 15 },
  "claude-3-haiku": { input: 0.25, output: 1.25 },
  "gemini-pro": { input: 0.5, output: 1.5 },
  "gemini-1.5-pro": { input: 3.5, output: 10.5 },
  "gemini-1.5-flash": { input: 0.075, output: 0.3 },
};

const decorationType = vscode.window.createTextEditorDecorationType({
  after: {
    margin: "0 0 0 1em",
    color: new vscode.ThemeColor("editorCodeLens.foreground"),
  },
});

export function updateAnnotations(
  editor: vscode.TextEditor,
  issues: ScanIssue[]
): void {
  const decorations: vscode.DecorationOptions[] = [];

  for (const issue of issues) {
    if (issue.lineNumber < 1 || issue.lineNumber > editor.document.lineCount) {
      continue;
    }
    const line = editor.document.lineAt(issue.lineNumber - 1);
    const cost = `$${issue.estimatedMonthlyCost.toFixed(2)}/mo`;
    const savings =
      issue.estimatedMonthlySavings > 0
        ? ` | Save $${issue.estimatedMonthlySavings.toFixed(2)}/mo with ${issue.recommendedModel}`
        : "";

    decorations.push({
      range: line.range,
      renderOptions: {
        after: {
          contentText: `  ← ${issue.provider}: ~${cost}${savings}`,
        },
      },
    });
  }

  editor.setDecorations(decorationType, decorations);
}

export function getLocalAnnotations(
  document: vscode.TextDocument
): vscode.DecorationOptions[] {
  const text = document.getText();
  const decorations: vscode.DecorationOptions[] = [];

  for (const { pattern, provider } of AI_CALL_PATTERNS) {
    const regex = new RegExp(pattern.source, "g");
    let match;
    while ((match = regex.exec(text)) !== null) {
      const pos = document.positionAt(match.index);
      const line = document.lineAt(pos.line);

      // Try to extract model name from nearby lines
      const contextStart = Math.max(0, pos.line - 3);
      const contextEnd = Math.min(document.lineCount - 1, pos.line + 5);
      let modelName = "";
      for (let i = contextStart; i <= contextEnd; i++) {
        const lineText = document.lineAt(i).text;
        const modelMatch = lineText.match(
          /model\s*[:=]\s*["']([^"']+)["']/
        );
        if (modelMatch) {
          modelName = modelMatch[1];
          break;
        }
      }

      const costs = modelName
        ? MODEL_COSTS[modelName] || MODEL_COSTS[modelName.split("-20")[0]]
        : undefined;

      let annotation = `  ← ${provider} API call`;
      if (modelName) {
        annotation += ` (${modelName})`;
      }
      if (costs) {
        annotation += ` | $${costs.input}/M input, $${costs.output}/M output`;
      }

      decorations.push({
        range: line.range,
        renderOptions: {
          after: {
            contentText: annotation,
          },
        },
      });
    }
  }

  return decorations;
}

export function clearAnnotations(editor: vscode.TextEditor): void {
  editor.setDecorations(decorationType, []);
}

export { decorationType };
