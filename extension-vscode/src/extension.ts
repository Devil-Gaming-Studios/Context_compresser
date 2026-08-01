import * as vscode from "vscode";
import { checkHealth, compressText, tokenize, CompressorApiError, CompressResponse, ModelName, PresetName } from "./api";

const BUDGETS: Record<string, { label: string; tokens: number }> = {
  "claude-200k": { label: "Claude 200K", tokens: 200_000 },
  "gpt4o-128k": { label: "GPT-4o 128K", tokens: 128_000 },
  "gpt4-8k": { label: "GPT-4 8K", tokens: 8_000 },
  "gemini-1m": { label: "Gemini 1M", tokens: 1_000_000 },
};

let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;
let lastReport: CompressResponse | undefined;
let tokenizeTimer: ReturnType<typeof setTimeout> | undefined;
let tokenizeGeneration = 0;

function cfg() {
  const c = vscode.workspace.getConfiguration("contextCompressor");
  return {
    apiBase: c.get<string>("apiBase", "https://context-compresser.onrender.com"),
    model: c.get<ModelName>("model", "claude"),
    preset: c.get<PresetName>("preset", "balanced"),
    targetCompression: c.get<number>("targetCompression", 70),
    contentType: c.get<"auto" | "code" | "logs" | "prose">("contentType", "auto"),
    liveTokenCounter: c.get<boolean>("liveTokenCounter", true),
    budgetPreset: c.get<string>("budgetPreset", "claude-200k"),
  };
}

function getSelectedTextOrWholeDoc(editor: vscode.TextEditor): { text: string; wasSelection: boolean } {
  const sel = editor.selection;
  if (!sel.isEmpty) {
    return { text: editor.document.getText(sel), wasSelection: true };
  }
  return { text: editor.document.getText(), wasSelection: false };
}

export function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel("Context Compressor");

  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = "contextCompressor.compressSelectionAndCopy";
  context.subscriptions.push(statusBarItem, outputChannel);

  context.subscriptions.push(
    vscode.commands.registerCommand("contextCompressor.compressSelectionAndCopy", compressSelectionAndCopy),
    vscode.commands.registerCommand("contextCompressor.compressSelectionReplace", compressSelectionReplace),
    vscode.commands.registerCommand("contextCompressor.compressFile", compressFilePreview),
    vscode.commands.registerCommand("contextCompressor.showReport", showReport),
    vscode.window.onDidChangeTextEditorSelection(() => scheduleTokenUpdate()),
    vscode.window.onDidChangeActiveTextEditor(() => scheduleTokenUpdate()),
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (vscode.window.activeTextEditor && e.document === vscode.window.activeTextEditor.document) {
        scheduleTokenUpdate();
      }
    }),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("contextCompressor")) scheduleTokenUpdate(true);
    })
  );

  scheduleTokenUpdate();
}

export function deactivate() {
  if (tokenizeTimer) clearTimeout(tokenizeTimer);
}

// --------------------------------------------------------------------------
// Live token counter (status bar)
// --------------------------------------------------------------------------

function scheduleTokenUpdate(immediate = false) {
  const { liveTokenCounter } = cfg();
  if (!liveTokenCounter) {
    statusBarItem.hide();
    return;
  }
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    statusBarItem.hide();
    return;
  }

  if (tokenizeTimer) clearTimeout(tokenizeTimer);
  const delay = immediate ? 0 : 300;
  tokenizeTimer = setTimeout(() => void updateTokenCount(editor), delay);
}

async function updateTokenCount(editor: vscode.TextEditor) {
  const generation = ++tokenizeGeneration;
  const { apiBase, model, budgetPreset } = cfg();
  const { text, wasSelection } = getSelectedTextOrWholeDoc(editor);

  if (!text.trim()) {
    statusBarItem.text = "$(circle-slash) Context Compressor: nothing to count";
    statusBarItem.tooltip = "Select text, or open a non-empty file, to see a live token count.";
    statusBarItem.show();
    return;
  }

  statusBarItem.text = `$(sync~spin) counting tokens…`;
  statusBarItem.show();

  try {
    const tokens = await tokenize(apiBase, text, model);
    if (generation !== tokenizeGeneration) return; // stale response, a newer request superseded this one

    const scope = wasSelection ? "selection" : "file";
    const budget = BUDGETS[budgetPreset];
    if (budget) {
      const pct = Math.min(999, Math.round((tokens / budget.tokens) * 100));
      statusBarItem.text = `$(symbol-numeric) ${tokens.toLocaleString()} tok (${scope}) · ${pct}% of ${budget.label}`;
      statusBarItem.tooltip =
        `${tokens.toLocaleString()} tokens in the current ${scope}, using the '${model}' tokenizer profile.\n` +
        `That's ${pct}% of ${budget.label}'s context window (${budget.tokens.toLocaleString()} tokens).\n` +
        `Click to compress and copy to clipboard.`;
    } else {
      statusBarItem.text = `$(symbol-numeric) ${tokens.toLocaleString()} tok (${scope})`;
      statusBarItem.tooltip = `${tokens.toLocaleString()} tokens in the current ${scope}. Click to compress and copy to clipboard.`;
    }
  } catch (err) {
    if (generation !== tokenizeGeneration) return;
    statusBarItem.text = "$(warning) Context Compressor: API unreachable";
    statusBarItem.tooltip = err instanceof Error ? err.message : String(err);
  }
}

// --------------------------------------------------------------------------
// Commands
// --------------------------------------------------------------------------

async function runCompression(text: string): Promise<CompressResponse | undefined> {
  const { apiBase, model, preset, targetCompression, contentType } = cfg();

  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "Context Compressor: compressing…" },
    async () => {
      try {
        const result = await compressText(apiBase, text, {
          model,
          preset,
          targetCompression,
          contentType,
        });
        lastReport = result;
        return result;
      } catch (err) {
        const message =
          err instanceof CompressorApiError
            ? err.message
            : `Unexpected error: ${err instanceof Error ? err.message : String(err)}`;
        const choice = await vscode.window.showErrorMessage(message, "Open Settings");
        if (choice === "Open Settings") {
          void vscode.commands.executeCommand("workbench.action.openSettings", "contextCompressor");
        }
        return undefined;
      }
    }
  );
}

function summaryMessage(r: CompressResponse): string {
  const pct = (r.compression_ratio * 100).toFixed(1);
  return `${r.original_tokens.toLocaleString()} → ${r.compressed_tokens.toLocaleString()} tokens (${pct}% smaller)`;
}

async function compressSelectionAndCopy() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return void vscode.window.showWarningMessage("Context Compressor: no active editor.");

  const { text, wasSelection } = getSelectedTextOrWholeDoc(editor);
  if (!text.trim()) {
    return void vscode.window.showWarningMessage("Context Compressor: nothing to compress.");
  }
  if (!wasSelection) {
    const choice = await vscode.window.showInformationMessage(
      "No selection -- compress the whole file?",
      { modal: true },
      "Compress Whole File"
    );
    if (choice !== "Compress Whole File") return;
  }

  const result = await runCompression(text);
  if (!result) return;

  await vscode.env.clipboard.writeText(result.compressed_text);

  const choice = await vscode.window.showInformationMessage(
    `Copied to clipboard: ${summaryMessage(result)}`,
    "Show Report"
  );
  if (choice === "Show Report") await showReport();
}

async function compressSelectionReplace() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return void vscode.window.showWarningMessage("Context Compressor: no active editor.");

  const sel = editor.selection;
  if (sel.isEmpty) {
    return void vscode.window.showWarningMessage(
      "Context Compressor: select the text you want compressed in place first."
    );
  }
  const text = editor.document.getText(sel);
  const result = await runCompression(text);
  if (!result) return;

  const applied = await editor.edit((editBuilder) => {
    editBuilder.replace(sel, result.compressed_text);
  });

  if (applied) {
    const choice = await vscode.window.showInformationMessage(
      `Replaced selection: ${summaryMessage(result)}`,
      "Undo",
      "Show Report"
    );
    if (choice === "Undo") await vscode.commands.executeCommand("undo");
    if (choice === "Show Report") await showReport();
  }
}

async function compressFilePreview() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return void vscode.window.showWarningMessage("Context Compressor: no active editor.");

  const text = editor.document.getText();
  if (!text.trim()) return void vscode.window.showWarningMessage("Context Compressor: file is empty.");

  const result = await runCompression(text);
  if (!result) return;

  const langId = editor.document.languageId;
  const doc = await vscode.workspace.openTextDocument({ language: langId, content: result.compressed_text });
  await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside, preview: true });

  const choice = await vscode.window.showInformationMessage(
    `Preview opened beside your file: ${summaryMessage(result)}. This preview isn't saved -- copy what you need.`,
    "Show Report"
  );
  if (choice === "Show Report") await showReport();
}

async function showReport() {
  if (!lastReport) {
    return void vscode.window.showInformationMessage("Context Compressor: run a compression first.");
  }
  const r = lastReport;
  outputChannel.clear();
  outputChannel.appendLine(`Context Compressor report`);
  outputChannel.appendLine(`${"=".repeat(40)}`);
  outputChannel.appendLine(`Original tokens:    ${r.original_tokens}`);
  outputChannel.appendLine(`Compressed tokens:  ${r.compressed_tokens}`);
  outputChannel.appendLine(`Reduction:          ${(r.compression_ratio * 100).toFixed(1)}%`);
  outputChannel.appendLine(`Chunks kept:        ${r.chunks_kept}/${r.chunks_total}`);
  outputChannel.appendLine(`Near-duplicates:    ${r.near_duplicates_removed} removed`);
  outputChannel.appendLine(`Structural lines:   ${r.structural_lines_collapsed} collapsed`);
  outputChannel.appendLine("");
  outputChannel.appendLine("Notes:");
  for (const note of r.notes) outputChannel.appendLine(`  - ${note}`);
  outputChannel.appendLine("");
  outputChannel.appendLine("Diff (- dropped / + kept):");
  for (const line of r.diff_lines) {
    outputChannel.appendLine(`${line.kept ? "+" : "-"} ${line.text}`);
  }
  outputChannel.show(true);
}
