import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

// Guardrails for headless pi operator runs (Mt. Moon speedrun):
//  1. bash calls get a default timeout (pi ships with none -> a hung probe blocked the run 21 min)
//  2. tool results are hard-capped at ~40KB so no extension can blow the 262k window again
const RELAY_TIMEOUT_S = Number(process.env.PI_GUARD_RELAY_TIMEOUT ?? 1800);   // relay.py legs
const DEFAULT_TIMEOUT_S = Number(process.env.PI_GUARD_DEFAULT_TIMEOUT ?? 300);  // everything else
const MAX_RESULT_BYTES = Number(process.env.PI_GUARD_MAX_RESULT ?? 40_000);

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    if (event.toolName === "bash") {
      const input = event.input as { command: string; timeout?: number };
      if (!input.timeout || input.timeout <= 0) {
        input.timeout = /relay\.py/.test(input.command) ? RELAY_TIMEOUT_S : DEFAULT_TIMEOUT_S;
      }
      // whole-log dumps were the other overflow source
      if (/(^|[;&|]\s*)cat\s+[^|]*agent\.log\s*$/.test(input.command)) {
        return { block: true, reason: "Do not cat whole agent.log files; use grep/tail/sed -n ranges." };
      }
    }
    if (event.toolName === "web_search" || event.toolName === "web_fetch") {
      return { block: true, reason: "web tools are disabled for this run (context overflow)." };
    }
    return undefined;
  });

  pi.on("tool_result", async (event) => {
    const content = (event as any).content as Array<{ type: string; text?: string }> | undefined;
    if (!content) return undefined;
    let changed = false;
    for (const part of content) {
      if (part.type === "text" && part.text && part.text.length > MAX_RESULT_BYTES) {
        part.text = part.text.slice(0, MAX_RESULT_BYTES) + `\n\n[guardrails: truncated ${part.text.length - MAX_RESULT_BYTES} more chars]`;
        changed = true;
      }
    }
    return changed ? { content } : undefined;
  });
}
