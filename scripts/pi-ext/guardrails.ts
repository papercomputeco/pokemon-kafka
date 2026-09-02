import * as fs from "node:fs";
import * as path from "node:path";
import { execFile } from "node:child_process";
import { pathToFileURL } from "node:url";
import { Type } from "typebox";
import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { buildSessionContext, SettingsManager } from "@mariozechner/pi-coding-agent";

// Guardrails for headless pi operator runs (Mt. Moon speedrun):
//  1. bash calls get a default timeout (pi ships with none -> a hung probe blocked the run 21 min)
//  2. tool results are hard-capped at ~40KB so no extension can blow the 262k window again
//  3. proactive context compaction at PI_GUARD_COMPACT_AT (default 75%) of the model's contextWindow.
//     pi's own auto-compaction only runs at agent_end / before the next prompt (agent-session.js
//     _checkCompaction), so in a headless `pi -p` run the window fills mid-loop and local Ollama
//     models return stopReason `length` (2026-08-16 laguna-xs / qwen38 runs died at ~130.8k/131k).
//     ctx.compact() exists but calls AgentSession.compact() -> abort(), which ends the run in print
//     mode; so we run pi's own compaction pipeline (prepareCompaction + compact + appendCompaction)
//     inside the `context` hook, which is awaited before every LLM call, and hand the LLM the
//     compacted view. The session jsonl gets a genuine `compaction` entry, same as /compact.
//  4. a one-shot deliverables nudge at PI_GUARD_NUDGE_AT (default 60%) via pi.sendMessage (steer).
const RELAY_TIMEOUT_S = Number(process.env.PI_GUARD_RELAY_TIMEOUT ?? 1800);   // relay.py legs
const DEFAULT_TIMEOUT_S = Number(process.env.PI_GUARD_DEFAULT_TIMEOUT ?? 300);  // everything else
const MAX_RESULT_BYTES = Number(process.env.PI_GUARD_MAX_RESULT ?? 40_000);
// Un-ranged `read` calls on big files are the local models' context sink: laguna-xs r2 (2026-08-16)
// read agent.py whole 8 times in 30 calls, each hitting the 40 KB cap (~10k tokens), so the window
// filled and compacted every ~2 minutes and each compaction forgot what was just read (compaction
// amnesia). Cap a `read` with no `limit` to this many lines; the model can page with offset/limit.
const READ_LIMIT_LINES = Number(process.env.PI_GUARD_READ_LIMIT ?? 200);
const COMPACT_AT = Number(process.env.PI_GUARD_COMPACT_AT ?? 0.75);   // fraction of contextWindow
const NUDGE_AT = Number(process.env.PI_GUARD_NUDGE_AT ?? 0.6);        // fraction of contextWindow
// A turn that stops with neither text nor a tool call ends the -p loop as if it were a final
// answer. Measured 2026-08-20 (expedition attempt 1): qwen38 emitted a 6.3k-char reasoning-only
// block, stopReason "stop", no content — pi exited 0 at 105 s into a 2 h leg and the guard read
// it as a dead stream. A followUp sent from turn_end starts a fresh turn (verified against this
// pi build), so steer such turns back to work, a bounded number of times per session.
const CONTINUE_MAX = Number(process.env.PI_GUARD_CONTINUE_MAX ?? 8);
const NUDGE_TEXT =
  "[guardrails] context is {pct}% used ({n}/{m} tokens). If this run has uncommitted work under docs/learnings " +
  "or scripts, commit it now; older history will be summarised (compacted) at {cpct}%.";

type CompactionModule = {
  prepareCompaction: (entries: unknown[], settings: unknown) => unknown | undefined;
  compact: (
    preparation: unknown,
    model: unknown,
    apiKey: string,
    headers: Record<string, string> | undefined,
    customInstructions: string | undefined,
    signal: AbortSignal | undefined,
    thinkingLevel?: unknown,
  ) => Promise<{ summary: string; firstKeptEntryId: string; tokensBefore: number; details?: unknown }>;
};

// pi's package index does not re-export prepareCompaction, and pi's jiti alias maps the bare
// package name to dist/index.js only, so load dist/core/compaction/compaction.js by absolute path.
async function loadCompactionModule(): Promise<CompactionModule | null> {
  const candidates: string[] = [];
  if (process.env.PI_GUARD_PI_DIST) candidates.push(process.env.PI_GUARD_PI_DIST);
  try {
    candidates.push(path.dirname(fs.realpathSync(process.argv[1] ?? "")));
  } catch {
    /* no argv[1] */
  }
  for (const dist of candidates) {
    const file = path.join(dist, "core", "compaction", "compaction.js");
    if (fs.existsSync(file)) {
      try {
        return (await import(pathToFileURL(file).href)) as CompactionModule;
      } catch (err) {
        console.error(`[guardrails] failed to import ${file}: ${(err as Error).message}`);
      }
    }
  }
  return null;
}

function notify(ctx: ExtensionContext, text: string) {
  console.error(text);
  if (ctx.hasUI) ctx.ui.notify(text, "info");
}

// number of session entries that materialise as LLM messages (mirrors buildSessionContext's appendMessage)
function persistedMessageCount(entries: Array<{ type: string; summary?: string }>): number {
  let n = 0;
  for (const e of entries) {
    if (e.type === "message" || e.type === "custom_message" || (e.type === "branch_summary" && e.summary)) n++;
  }
  return n;
}

// The Oracle (scripts/advisor.py oracle): a knowledge bearer over docs/learnings, evals, benchmarks and
// past sessions (tapes). Exposed to the operator as `consult` so a driver-class model can ask "have
// we seen this before?" instead of re-reading agent.py after every compaction (SUMMARY §10, #79).
const REPO_ROOT = process.env.PI_GUARD_REPO ?? path.resolve(path.dirname(new URL(import.meta.url).pathname), "..", "..");
const CONSULT_TIMEOUT_MS = Number(process.env.PI_GUARD_CONSULT_TIMEOUT ?? 120_000);
// OPT-IN. Baseline benchmark rows measure the model alone; a run with the Oracle is a different row
// (assist=consult) and must never be compared to an unassisted one. Enable with PI_GUARD_CONSULT=1.
const CONSULT_ENABLED = process.env.PI_GUARD_CONSULT === "1";

function runOracle(question: string): Promise<string> {
  return new Promise((resolve) => {
    execFile(
      "uv",
      ["run", "python", "scripts/advisor.py", "oracle", question, "-k", "6"],
      { cwd: REPO_ROOT, timeout: CONSULT_TIMEOUT_MS, maxBuffer: 1 << 20 },
      (err, stdout, stderr) => {
        if (err && !stdout) resolve(`[consult] oracle unavailable: ${String(stderr || err.message).slice(0, 400)}`);
        else resolve(String(stdout).trim() || "NO PRECEDENT");
      },
    );
  });
}

export default async function (pi: ExtensionAPI) {
  if (CONSULT_ENABLED) pi.registerTool({
    name: "consult",
    label: "Consult the Oracle",
    description:
      "Ask the project's Oracle whether this obstacle has been seen before. It answers ONLY from recorded " +
      "learnings, eval cases/results, benchmark rows and past captured sessions, with citations (path:line or " +
      "session id), or says NO PRECEDENT. Use it before re-reading code after a failed relay: describe the " +
      "symptom concretely (map id, position, HP, the repeated action, stuck streak).",
    promptSnippet: "consult(question): cited precedent from past runs, learnings and evals — or NO PRECEDENT",
    promptGuidelines: [
      "When a relay segment fails with identical lanes, call consult with the concrete symptom before reading whole files.",
    ],
    parameters: Type.Object({
      question: Type.String({ description: "The concrete symptom or question, e.g. 'lanes stall on map 54 pressing up, stuck streak 2800'" }),
    }),
    async execute(_id, params) {
      const text = await runOracle(params.question);
      return { content: [{ type: "text", text }], details: {} } as any;
    },
  } as any);

  const compaction = await loadCompactionModule();
  if (!compaction) {
    console.error("[guardrails] compaction module not found; compaction guard disabled (set PI_GUARD_PI_DIST=<pi>/dist)");
  }
  let nudged = false;
  let revived = 0; // reasoning-only continuations sent this session
  let compacting = false;
  let guardCompacted = false; // we appended a compaction the agent's own state does not know about

  pi.on("session_start", () => {
    nudged = false;
    revived = 0;
    guardCompacted = false;
  });
  // pi's own compaction (agent_end / manual) rebuilds agent state from the session, so drop our overlay
  pi.on("session_compact", () => {
    guardCompacted = false;
  });

  pi.on("tool_call", async (event) => {
    if (event.toolName === "read") {
      const input = event.input as { path?: string; offset?: number; limit?: number };
      if (READ_LIMIT_LINES > 0 && (!input.limit || input.limit <= 0 || input.limit > READ_LIMIT_LINES)) {
        input.limit = READ_LIMIT_LINES;
        if (!input.offset || input.offset <= 0) input.offset = 1;
      }
    }
    if (event.toolName === "bash") {
      const input = event.input as { command: string; timeout?: number };
      if (!input.timeout || input.timeout <= 0) {
        input.timeout = /relay\.py/.test(input.command) ? RELAY_TIMEOUT_S : DEFAULT_TIMEOUT_S;
      }
      // whole-log dumps were the other overflow source
      if (/(^|[;&|]\s*)cat\s+[^|]*agent\.log\s*$/.test(input.command)) {
        return { block: true, reason: "Do not cat whole agent.log files; use grep/tail/sed -n ranges." };
      }
      // `pkill -f <pattern>` matches the AGENT'S OWN command line, because the pattern is a
      // literal substring of it. Two badge-8 legs ended themselves this way with
      // `pkill -f "supervisor.py run"` -- the run dies mid-mission and looks like a crash. A
      // written warning in the mission did not stop the second one, so it is enforced here.
      // A bracketed pattern (`supervisor[.]py`) cannot match itself and is allowed through.
      const pkillF = /\bpkill\s+(?:-\w+\s+)*-\w*f\w*\s+(\S+)/.exec(input.command);
      if (pkillF && !pkillF[1].includes("[")) {
        return {
          block: true,
          reason:
            `pkill -f ${pkillF[1]} would match this shell's own command line and kill your run — ` +
            "two legs have already died this way. Kill by PID (`kill 12345`, from a saved $! or " +
            "pgrep in a SEPARATE command), or bracket the pattern so it cannot match itself " +
            "(e.g. supervisor[.]py).",
        };
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

  // Deliverables nudge: once per session, delivered as a steering message before the next LLM call.
  pi.on("turn_end", async (event, ctx) => {
    // Reasoning-only stop: no text, no tool call — without this followUp, the loop ends here.
    const msg = (event as any)?.message ?? {};
    const parts = Array.isArray(msg.content) ? msg.content : [];
    const hasText = parts.some((b: any) => b.type === "text" && b.text && b.text.trim());
    const hasTool = parts.some((b: any) => b.type === "toolCall");
    if (msg.role === "assistant" && !hasText && !hasTool && revived < CONTINUE_MAX) {
      revived++;
      const cont =
        `[guardrails] your last turn produced no text and no tool call (reasoning only) — the harness ` +
        `treats that as mission end. Continue the mission: state your next action as text and run it. ` +
        `(continuation ${revived}/${CONTINUE_MAX})`;
      console.error(cont);
      pi.sendMessage({ customType: "guardrails-continue", content: cont, display: true }, { deliverAs: "followUp" });
      return;
    }
    if (nudged) return;
    const usage = ctx.getContextUsage();
    if (!usage || usage.tokens === null || usage.contextWindow <= 0) return;
    if (usage.tokens < NUDGE_AT * usage.contextWindow) return;
    nudged = true;
    const text = NUDGE_TEXT.replace("{pct}", Math.round((usage.tokens / usage.contextWindow) * 100).toString())
      .replace("{n}", usage.tokens.toString())
      .replace("{m}", usage.contextWindow.toString())
      .replace("{cpct}", Math.round(COMPACT_AT * 100).toString());
    console.error(text);
    pi.sendMessage({ customType: "guardrails-nudge", content: text, display: true }, { deliverAs: "steer" });
  });

  // Compaction guard: runs before every LLM call.
  pi.on("context", async (event, ctx) => {
    if (!compaction) return undefined;
    const sm = ctx.sessionManager as unknown as {
      getBranch: () => Array<{ type: string; summary?: string }>;
      appendCompaction?: (summary: string, firstKeptEntryId: string, tokensBefore: number, details?: unknown, fromHook?: boolean) => string;
    };
    const model = ctx.model;
    const usage = ctx.getContextUsage();
    const contextWindow = usage?.contextWindow ?? model?.contextWindow ?? 0;
    const tokens = usage?.tokens ?? null;
    const shouldCompact =
      !compacting && model && tokens !== null && contextWindow > 0 && tokens >= COMPACT_AT * contextWindow && typeof sm.appendCompaction === "function";

    if (shouldCompact) {
      compacting = true;
      try {
        const settings = SettingsManager.create(ctx.cwd).getCompactionSettings();
        const branch = sm.getBranch();
        const preparation = compaction.prepareCompaction(branch, settings);
        if (!preparation) {
          console.error(`[guardrails] at ${tokens}/${contextWindow} tokens but nothing to compact (session too small or already compacted)`);
        } else {
          notify(ctx, `[guardrails] compacting at ${tokens}/${contextWindow} tokens`);
          const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
          if (!auth.ok) throw new Error(auth.error);
          const result = await compaction.compact(preparation, model, auth.apiKey ?? "", auth.headers, undefined, ctx.signal);
          sm.appendCompaction!(result.summary, result.firstKeptEntryId, result.tokensBefore, result.details, false);
          guardCompacted = true;
          notify(ctx, `[guardrails] compaction done: ${result.tokensBefore} tokens summarised, kept from ${result.firstKeptEntryId}`);
        }
      } catch (err) {
        console.error(`[guardrails] compaction failed: ${(err as Error).message}`);
      } finally {
        compacting = false;
      }
    }

    if (!guardCompacted) return undefined;
    // The agent's own message list still holds the full history; hand the LLM the session view
    // (summary + kept + later messages) plus any trailing messages not yet persisted.
    const branch = sm.getBranch();
    const view = buildSessionContext(branch as any).messages as typeof event.messages;
    const tail = event.messages.slice(persistedMessageCount(branch));
    return { messages: [...view, ...tail] };
  });
}
