#!/usr/bin/env python3
"""Build the local-vs-Haiku benchmark artifact (HTML) from the measured numbers."""

import html
import json
import sys
from pathlib import Path

OUT = Path(__file__).with_name("local-vs-haiku.html")  # publish this file as the "Local vs Haiku" artifact
RELAY_JSON = Path(__file__).with_name("relay_result.json")  # qwen3-coder run
RELAY_RUNS_JSON = Path(__file__).with_name("relay_runs.json")  # list of later runs (laguna, qwen38...)

HAIKU = {"tok_s": 91.9, "s_turn": 4.8, "segs": "2/4", "usd": 0.87, "wall_m": 67}

# alias, group, out tok/s, prompt tok/s, resident GB, peak W, mean W, note
PROBE = [
    ("laguna-xs", "moe", 315.8, 7662, 20.9, 354, 340, "Poolside Laguna XS 2.1 · 33B-A3B"),
    ("qwen3-coder-30b", "moe", 302.7, 15189, 25.6, 359, 341, "Qwen3-Coder 30B-A3B"),
    ("gpt-oss-20b", "moe", 299.2, 26502, 13.6, 488, 443, "OpenAI gpt-oss 20B MXFP4"),
    ("qwen36-35b", "moe", 255.6, 2596, 24.4, 349, 321, "Qwen3.6 35B MoE"),
    ("qwen35b", "moe", 251.9, 2498, 24.4, 331, 302, "Qwen3.5 35B-A3B · 08-15 baseline"),
    ("glm47-flash", "moe", 242.7, 12302, 23.0, 359, 335, "GLM-4.7-Flash 30B MoE"),
    ("gemma4", "dense", 233.9, 6580, 4.1, 380, 345, "Gemma 4 E4B · 08-15 baseline"),
    ("nemotron35-lightning", "moe", 215.0, 3577, 25.5, 299, 285, "NVIDIA Nemotron 3.5 Lightning 30B-A3B"),
    ("qwen38-27b", "dense", 130.0, 643, 17.9, 602, 233, "Qwen3.8 27B dense"),
    ("muse-glimmer", "dense", 81.4, 3784, 16.7, 569, 549, "Muse Glimmer 27.9B dense"),
    ("gemma4-31b", "dense", 67.3, 1583, 20.8, 573, 546, "Gemma 4 31B dense"),
]

# alias, overall, context-discipline, flee-loop-cap, pewter-waypoint-wall, transition-save, no-answer, tok/s, wall s
T = None  # truncated
EVALS = [
    ("qwen38-27b", 0.79, 1.00, 1.00, 0.56, 0.60, 0, 141, 99.8),
    ("qwen3-coder-30b", 0.69, 0.80, 0.82, 0.56, 0.60, 0, 290, 10.6),
    ("muse-glimmer", 0.61, 0.80, 0.27, 0.78, 0.60, 0, 80, 172.2),
    ("gemma4-31b", 0.61, 0.80, 0.55, 0.78, 0.30, 0, 66, 118.2),
    ("gpt-oss-20b", 0.57, 0.60, 0.00, 0.78, 0.90, 0, 292, 26.2),
    ("gemma4", 0.43, 0.60, 0.27, 0.56, 0.30, 0, 231, 26.1),
    ("laguna-xs", 0.42, T, T, 0.78, 0.90, 2, 303, 41.1),
    ("qwen35b", 0.36, T, T, 0.56, 0.90, 2, 257, 58.6),
    ("qwen36-35b", 0.34, T, T, 0.78, 0.60, 2, 256, 61.7),
    ("nemotron35-lightning", 0.21, 0.50, T, 0.33, 0.00, 1, 221, 66.1),
    ("glm47-flash", 0.06, T, T, 0.22, T, 3, 223, 71.4),
]
CASES = ["context-discipline", "flee-loop-cap", "pewter-waypoint-wall", "transition-save-corruption"]
GROUP = {a: g for a, g, *_ in PROBE}

# 2026-08-15 relay scoreboard (pi harness, 64k, five models) — for the relay section's context
RELAY_0815 = [
    ("Sonnet 5", "cloud", "2/4", 49, 28.9, 186, 72.8, 9.3, "6.86", "yes"),
    ("Kimi K2.6", "cloud", "2/4", 158, 34.8, 190, 56.4, 11.0, "≥25.87", "yes"),
    ("Haiku 4.5", "cloud", "2/4", 67, 5.9, 74, 91.9, 4.8, "0.87", "no"),
    ("Qwen3.5-35B (local, 64k)", "local", "2/4", 38, 27.1, 101, 20.1, 16.1, "0.73 eq.", "edits, uncommitted"),
    ("Gemma4 E4B (local, 64k)", "local", "2/4", 15, 0.9, 29, 142.9, 1.9, "0.15 eq.", "no"),
]


def e(s):
    return html.escape(str(s))


# ----------------------------------------------------------------------------- charts


def bar_chart():
    """Horizontal bars: out tok/s per model, colored by group, Haiku reference rule."""
    rows = PROBE
    w, lab_w, right = 880, 190, 70
    row_h, bar_h = 30, 18
    h = row_h * len(rows) + 60
    maxv = 340
    scale = (w - lab_w - right) / maxv
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-labelledby="bar-title">']
    parts.append('<title id="bar-title">Decode speed at 128k context, out tokens per second</title>')
    top = 22
    # gridlines
    for v in range(0, maxv + 1, 50):
        x = lab_w + v * scale
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{h - 34}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{h - 16}" class="tick" text-anchor="middle">{v}</text>')
    for i, (alias, g, tok, ptok, gb, pk, mean, note) in enumerate(rows):
        y = top + 6 + i * row_h
        bw = tok * scale
        parts.append(
            f'<g class="bar-row" data-tip="{e(note)} — {tok} tok/s · prompt {ptok:,} tok/s · {gb} GB resident · '
            f'peak {pk} W · mean {mean} W">'
            f'<rect x="{lab_w - 4}" y="{y - 4}" width="{w - lab_w - right + 8}" height="{row_h - 2}" class="hit"/>'
            f'<text x="{lab_w - 10}" y="{y + bar_h / 2 + 4}" class="lbl" text-anchor="end">{e(alias)}</text>'
            f'<path d="M{lab_w},{y} h{bw - 4:.1f} a4,4 0 0 1 4,4 v{bar_h - 8} a4,4 0 0 1 -4,4 '
            f'h{-(bw - 4):.1f} z" class="s-{g}"/>'
            f'<text x="{lab_w + bw + 8:.1f}" y="{y + bar_h / 2 + 4}" class="val">{tok:g}</text>'
            f"</g>"
        )
    hx = lab_w + HAIKU["tok_s"] * scale
    parts.append(f'<line x1="{hx:.1f}" y1="{top - 4}" x2="{hx:.1f}" y2="{h - 34}" class="ref"/>')
    parts.append(f'<text x="{hx + 6:.1f}" y="{top - 8}" class="reflbl">Haiku 4.5 · {HAIKU["tok_s"]} tok/s</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def scatter():
    """out tok/s (x) vs eval overall (y). The page's thesis chart."""
    w, h = 880, 400
    ml, mr, mt, mb = 60, 40, 24, 44
    pw, ph = w - ml - mr, h - mt - mb
    xmax, ymax = 340, 1.0

    def sx(v):
        return ml + v / xmax * pw

    def sy(v):
        return mt + (1 - v / ymax) * ph

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-labelledby="sc-title">']
    parts.append('<title id="sc-title">Decode speed against diagnostic eval score</title>')
    for v in range(0, xmax + 1, 50):
        parts.append(f'<line x1="{sx(v):.1f}" y1="{mt}" x2="{sx(v):.1f}" y2="{mt + ph}" class="grid"/>')
        parts.append(f'<text x="{sx(v):.1f}" y="{h - 14}" class="tick" text-anchor="middle">{v}</text>')
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        parts.append(f'<line x1="{ml}" y1="{sy(v):.1f}" x2="{ml + pw}" y2="{sy(v):.1f}" class="grid"/>')
        parts.append(f'<text x="{ml - 10}" y="{sy(v) + 4:.1f}" class="tick" text-anchor="end">{v:.2f}</text>')
    hx = sx(HAIKU["tok_s"])
    parts.append(f'<line x1="{hx:.1f}" y1="{mt}" x2="{hx:.1f}" y2="{mt + ph}" class="ref"/>')
    parts.append(f'<text x="{hx + 6:.1f}" y="{mt + 14}" class="reflbl">Haiku 4.5 decode</text>')
    parts.append(
        f'<text x="{ml + pw / 2:.1f}" y="{h - 1}" class="axis" text-anchor="middle">out tok/s (128k ctx)</text>'
    )
    parts.append(
        f'<text transform="translate(14,{mt + ph / 2:.1f}) rotate(-90)" class="axis" text-anchor="middle">eval overall</text>'
    )
    tok_of = {r[0]: r[2] for r in PROBE}
    label_these = {"qwen3-coder-30b", "qwen38-27b", "laguna-xs", "glm47-flash", "gpt-oss-20b", "gemma4-31b"}
    for alias, overall, *cases, noans, tok, wall in EVALS:
        x, y = sx(tok_of[alias]), sy(overall)
        g = GROUP[alias]
        tr = " trunc" if noans else ""
        tip = f"{alias} — {overall:.2f} overall · {tok} tok/s · {wall} s wall · {noans} unanswered"
        parts.append(
            f'<g class="dot{tr}" data-tip="{e(tip)}"><circle cx="{x:.1f}" cy="{y:.1f}" r="14" class="hit"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" class="s-{g} ring"/>'
            + (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" class="trunc-ring"/>' if noans else "")
            + (
                (
                    f'<text x="{x - 12:.1f}" y="{y + 4:.1f}" class="lbl" text-anchor="end">{e(alias)}</text>'
                    if tok_of[alias] > 240
                    else f'<text x="{x + 12:.1f}" y="{y + 4:.1f}" class="lbl">{e(alias)}</text>'
                )
                if alias in label_these
                else ""
            )
            + "</g>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def eval_table():
    head = "".join(f"<th>{e(c)}</th>" for c in CASES)
    out = [
        '<table class="data"><thead><tr><th>model</th><th>overall</th>'
        + head
        + "<th>no answer</th><th>tok/s</th><th>wall s</th></tr></thead><tbody>"
    ]
    for alias, overall, *cases, noans, tok, wall in EVALS:
        cells = []
        for v in cases:
            if v is None:
                cells.append('<td class="tr"><span class="chip crit">trunc</span></td>')
            else:
                cells.append(f'<td><span class="cell-bar" style="--v:{v:.2f}"></span>{v:.2f}</td>')
        out.append(
            f'<tr><td class="name"><i class="sw s-{GROUP[alias]}"></i>{e(alias)}</td><td class="strong">{overall:.2f}</td>'
            + "".join(cells)
            + f"<td>{noans or '—'}</td><td>{tok}</td><td>{wall}</td></tr>"
        )
    out.append("</tbody></table>")
    return "\n".join(out)


def probe_table():
    out = [
        '<table class="data"><thead><tr><th>model</th><th>group</th><th>out tok/s</th><th>prompt tok/s</th><th>resident GB</th><th>peak W</th><th>mean W</th></tr></thead><tbody>'
    ]
    for alias, g, tok, ptok, gb, pk, mean, note in PROBE:
        out.append(
            f'<tr><td class="name"><i class="sw s-{g}"></i>{e(alias)}<small>{e(note)}</small></td><td>{g}</td>'
            f'<td class="strong">{tok:g}</td><td>{ptok:,}</td><td>{gb}</td><td>{pk}</td><td>{mean}</td></tr>'
        )
    out.append("</tbody></table>")
    return "\n".join(out)


def relay_section():
    r = json.loads(RELAY_JSON.read_text()) if RELAY_JSON.exists() else None
    runs = json.loads(RELAY_RUNS_JSON.read_text()) if RELAY_RUNS_JSON.exists() else []

    def row(m, src, segs, wall, mm, turns, tok, st, usd, fix, cls=""):
        sw = "s-moe" if src == "local" else "s-ref"
        return (
            f'<tr class="{cls}"><td class="name"><i class="sw {sw}"></i>{e(m)}</td><td>{src}</td><td class="strong">{e(segs)}</td>'
            f"<td>{e(wall)}</td><td>{e(mm)}</td><td>{e(turns)}</td><td>{e(tok)}</td><td>{e(st)}</td><td>{e(usd)}</td><td>{e(fix)}</td></tr>"
        )

    rows = ""
    for x in runs:
        rows += row(
            x["model"],
            "local",
            x["segs"],
            x["wall_m"],
            x["model_m"],
            x["turns"],
            x["tok_s"],
            x["s_turn"],
            x["cloud_usd"],
            x["code_fix"],
        )
    if r:
        rows += row(
            "qwen3-coder-30b (local, 128k) — retired",
            "local",
            r["segs"],
            r["wall_m"],
            r["model_m"],
            r["turns"],
            r["tok_s"],
            r["s_turn"],
            r["cloud_usd"],
            r["code_fix"],
        )
    for m, src, segs, wall, mm, turns, tok, st, usd, fix in RELAY_0815:
        rows += row(m, src, segs, wall, mm, turns, tok, st, usd, fix)
    stories = ""
    for x in runs:
        stories += f"""
<div class="col">
<h3>{e(x["model"])} — {e(x["headline"])}</h3>
<ol>{"".join(f"<li>{step}</li>" for step in x["steps"])}</ol>
<div class="callout"><p>{x["callout"]}</p></div>
<p class="note"><strong>Measured energy:</strong> {e(x["wh"])} Wh ({e(x["mean_w"])} W GPU mean, {e(x["peak_w"])} W peak) → ${e(x["energy_usd"])} at $0.30/kWh. {x.get("energy_note", "")}</p>
</div>"""
    if r:
        stories += f"""
<div class="col">
<h3>qwen3-coder-30b — 0/4 in 12 minutes, retired from the roster</h3>
<ol>
<li>All six <code>route1_to_forest</code> lanes ended identically: 2000 turns, lead at 4/23 HP, <code>Action: run</code> against a Lv3 Weedle until the budget ran out — <strong>the flee-loop bug from the learnings, the case this model scored 0.82 on when handed the code.</strong></li>
<li>It never opened <code>agent.py</code>, <code>report.json</code>, or a lane's <code>fitness.json</code>. It re-ran with <code>--timeout 60</code> (every lane killed at 60 s), then the next segment the same way, and concluded the harness was misconfigured.</li>
<li>It wrote learnings for Brock and Route 3 — obstacles it never reached — and a summary claiming ~45 minutes at the 8-minute mark. Then it exited at 12 minutes: <em>"ALL TASK REQUIREMENTS COMPLETED SUCCESSFULLY."</em></li>
</ol>
<div class="callout"><p><strong>Recognizing a bug when shown the code and finding it from a run are different skills.</strong> The eval measures the first; the relay measures the second. Asked directly, this model names <code>choose_action</code>; running autonomously it never opened it. Tuned to edit code it is pointed at, no thinking mode — a fixer, not an investigator. Retired.</p></div>
<p class="note"><strong>Measured energy:</strong> {e(r["wh"])} Wh ({e(r["mean_w"])} W GPU mean, {e(r["peak_w"])} W peak) → ${e(r["energy_usd"])}. Cloud-equivalent $0.57 is almost entirely 3.88 M <em>uncached</em> input tokens.</p>
</div>"""
    nxt = """
<div class="col">
<h3>Next</h3>
<ul>
<li>Rerun <code>qwen38-27b</code> — its first attempt was killed by a GPU crash (<code>CUDA error: the launch timed out</code>) while it was diagnosing correctly; the harness reported it as the model stopping. No local row is a verdict until the Ollama journal is clean for the run window.</li>
<li>Rerun <code>laguna-xs</code> with a compaction guard — the 128k window filled while it was on the right thread; pi only compacts on a 400 and local models return <code>length</code> instead.</li>
<li>The two skills measured here — investigate vs. fix — do not live in the same 30B model today. Consider splitting the operator.</li>
</ul>
</div>"""
    return f"""
<div class="wide"><table class="data"><thead><tr><th>model</th><th>src</th><th>segs</th><th>wall m</th><th>model m</th><th>turns</th><th>out tok/s</th><th>s/turn</th><th>cloud $</th><th>code fix</th></tr></thead>
<tbody>{rows}</tbody></table></div>
{stories}{nxt}
"""


# ----------------------------------------------------------------------------- page

CSS = """
:root{
  --bg:#F4F5F1; --bg2:#EAECE5; --ink:#1B221D; --ink2:#4E5953; --ink3:#7A857E; --rule:#D5DAD3;
  --moe:#3B6E2A; --dense:#3E6FA8; --ref:#1B221D; --crit:#d03b3b; --ok:#0ca30c; --live:#B4602A;
  --moe-wash:rgba(59,110,42,.10); --dense-wash:rgba(62,111,168,.10);
  --tip-bg:#1B221D; --tip-ink:#F4F5F1;
  --serif:"Iowan Old Style","Palatino Linotype","Book Antiqua",Palatino,Georgia,serif;
  --sans:"Avenir Next","Segoe UI","Helvetica Neue",system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#151A17; --bg2:#1E2622; --ink:#E4E9E3; --ink2:#A9B3AC; --ink3:#7C877F; --rule:#2B332E;
  --moe:#6FA556; --dense:#5B8FD0; --ref:#E4E9E3; --crit:#e66767; --ok:#3fbf3f; --live:#D9895A;
  --moe-wash:rgba(111,165,86,.14); --dense-wash:rgba(91,143,208,.14);
  --tip-bg:#E4E9E3; --tip-ink:#151A17;
}}
:root[data-theme="dark"]{
  --bg:#151A17; --bg2:#1E2622; --ink:#E4E9E3; --ink2:#A9B3AC; --ink3:#7C877F; --rule:#2B332E;
  --moe:#6FA556; --dense:#5B8FD0; --ref:#E4E9E3; --crit:#e66767; --ok:#3fbf3f; --live:#D9895A;
  --moe-wash:rgba(111,165,86,.14); --dense-wash:rgba(91,143,208,.14);
  --tip-bg:#E4E9E3; --tip-ink:#151A17;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:17px;line-height:1.55;-webkit-font-smoothing:antialiased}
main{max-width:1040px;margin:0 auto;padding:56px 24px 96px}
.col{max-width:68ch}
h1,h2,h3{font-family:var(--serif);font-weight:500;letter-spacing:-.005em;text-wrap:balance;margin:0}
h1{font-size:clamp(34px,5vw,50px);line-height:1.08}
h2{font-size:28px;margin:64px 0 12px}
h3{font-size:20px;margin:28px 0 8px}
p{margin:0 0 14px}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink3);margin-bottom:14px}
.lede{font-size:21px;line-height:1.45;color:var(--ink2);margin:16px 0 30px;max-width:60ch}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:8px 0 8px}
.tile{background:var(--bg2);border-radius:6px;padding:16px 18px 14px;display:flex;flex-direction:column;gap:6px}
.tile .l{font-size:13px;color:var(--ink2)}
.tile .v{font-family:var(--mono);font-size:30px;font-variant-numeric:tabular-nums;line-height:1;display:flex;align-items:baseline;gap:6px}
.tile .v small{font-size:13px;color:var(--ink3);font-family:var(--sans)}
.tile .c{font-size:13px;color:var(--ink3);display:flex;align-items:center;gap:6px}
.wide{margin:18px 0 8px;overflow-x:auto}
.chart{width:100%;height:auto;display:block;font-family:var(--sans)}
.chart .grid{stroke:var(--rule);stroke-width:1}
.chart .tick,.chart .axis{fill:var(--ink3);font-size:11px;font-family:var(--mono)}
.chart .axis{font-family:var(--sans);font-size:12px}
.chart .lbl{fill:var(--ink);font-size:13px;font-family:var(--mono)}
.chart .val,.chart .lbl,.chart .reflbl{paint-order:stroke;stroke:var(--bg);stroke-width:4px;stroke-linejoin:round}
.chart .val{fill:var(--ink2);font-size:12px;font-family:var(--mono);font-variant-numeric:tabular-nums}
.chart .ref{stroke:var(--ref);stroke-width:2;stroke-linecap:round}
.chart .reflbl{fill:var(--ink);font-size:12px;font-family:var(--sans);font-weight:600}
.chart .hit{fill:transparent}
.chart .bar-row:hover .hit,.chart .dot:hover .hit{fill:var(--bg2)}
.chart .ring{stroke:var(--bg);stroke-width:2}
.chart .trunc-ring{fill:none;stroke:var(--crit);stroke-width:2}
.s-moe{fill:var(--moe);background:var(--moe)} .s-dense{fill:var(--dense);background:var(--dense)} .s-ref{fill:var(--ref);background:var(--ref)}
.legend{display:flex;flex-wrap:wrap;gap:18px;font-size:13px;color:var(--ink2);margin:6px 0 4px}
.legend span{display:inline-flex;align-items:center;gap:7px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:8px;vertical-align:1px}
.sw.ref{background:var(--ref)} .sw.crit{background:none;border:2px solid var(--crit);border-radius:50%;width:9px;height:9px}
.line-key{display:inline-block;width:14px;height:2px;background:var(--ref)}
table.data{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
table.data th{font-family:var(--mono);font-weight:500;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3);text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule);white-space:nowrap}
table.data td{padding:9px 10px;border-bottom:1px solid var(--rule);vertical-align:top;font-family:var(--mono);white-space:nowrap}
table.data td.name{font-family:var(--sans);font-weight:500}
table.data td.name small{display:block;font-weight:400;color:var(--ink3);font-size:12px;white-space:normal}
table.data td.strong{font-weight:600;color:var(--ink)}
table.data tr.pending td{color:var(--ink3);font-style:italic;font-family:var(--sans)}
.cell-bar{display:inline-block;width:44px;height:6px;border-radius:3px;background:var(--rule);margin-right:8px;vertical-align:middle;position:relative;overflow:hidden}
.cell-bar::after{content:"";position:absolute;inset:0;width:calc(var(--v)*100%);background:var(--moe);border-radius:3px}
.chip{display:inline-block;font-family:var(--mono);font-size:11px;letter-spacing:.04em;padding:2px 7px;border-radius:3px;border:1px solid currentColor;line-height:1.5}
.chip.crit{color:var(--crit)} .chip.ok{color:var(--ok)} .chip.live{color:var(--live)}
.status{font-family:var(--mono);font-size:13px;color:var(--ink2);margin:6px 0 0}
.note{font-size:15px;color:var(--ink2);border-left:2px solid var(--rule);padding-left:14px;margin:18px 0}
.callout{background:var(--bg2);border-radius:6px;padding:18px 20px;margin:22px 0}
.callout p:last-child{margin:0}
ol,ul{padding-left:1.2em} li{margin-bottom:6px}
code{font-family:var(--mono);font-size:.9em;background:var(--bg2);padding:1px 5px;border-radius:3px}
.tip{position:fixed;pointer-events:none;background:var(--tip-bg);color:var(--tip-ink);font-family:var(--mono);font-size:12px;padding:6px 9px;border-radius:4px;max-width:340px;white-space:normal;line-height:1.4;opacity:0;transform:translate(-50%,-120%);transition:opacity .08s;z-index:9}
.tip.on{opacity:1}
.foot{margin-top:72px;font-size:13px;color:var(--ink3);border-top:1px solid var(--rule);padding-top:16px}
@media (prefers-reduced-motion: reduce){.tip{transition:none}}
"""

JS = """
(function(){
  var tip=document.createElement('div');tip.className='tip';document.body.appendChild(tip);
  function show(el,ev){tip.textContent=el.getAttribute('data-tip');tip.classList.add('on');move(ev);}
  function move(ev){tip.style.left=ev.clientX+'px';tip.style.top=(ev.clientY-10)+'px';}
  function hide(){tip.classList.remove('on');}
  document.querySelectorAll('[data-tip]').forEach(function(el){
    el.addEventListener('mouseenter',function(ev){show(el,ev)});
    el.addEventListener('mousemove',move);
    el.addEventListener('mouseleave',hide);
    el.setAttribute('tabindex','0');
    el.addEventListener('focus',function(){var r=el.getBoundingClientRect();show(el,{clientX:r.left+r.width/2,clientY:r.top});});
    el.addEventListener('blur',hide);
  });
})();
"""


def page():
    return f"""<title>Local vs Haiku</title>
<style>{CSS}</style>
<main>
<p class="eyebrow">pcc-labs / pokemon-kafka · benchmarks · 2026-08-15 → 16</p>
<h1>Local vs Haiku</h1>
<p class="lede">Can an open model running on one RTX 5090 match Haiku 4.5 as the operator of a Pokémon Red speedrun harness? Three measurements, taken in order: how fast each model decodes at 128k context, how well it diagnoses the obstacles the last five runs actually hit, and then real relay runs with the power meter on. The probes picked one model; the runs picked another.</p>

<div class="tiles">
  <div class="tile"><span class="l">Fastest local decode</span><span class="v">316<small>tok/s</small></span><span class="c"><i class="sw s-moe"></i>laguna-xs · 3.4× Haiku</span></div>
  <div class="tile"><span class="l">Best diagnosis score</span><span class="v">0.79<small>/ 1</small></span><span class="c"><i class="sw s-dense"></i>qwen38-27b · 141 tok/s</span></div>
  <div class="tile"><span class="l">Best local relay run</span><span class="v">2<small>/ 4 segs</small></span><span class="c"><i class="sw s-moe"></i>laguna-xs · 91 tok/s · 4.0 s/turn · 78 Wh</span></div>
  <div class="tile"><span class="l">The bar to clear</span><span class="v">91.9<small>tok/s</small></span><span class="c"><i class="sw ref"></i>Haiku 4.5 · 2/4 segs · $0.87</span></div>
</div>

<div class="col">
<h2>Setup</h2>
<p>Ollama 0.32.13 on an RTX 5090 (32 GB) with flash attention and a q8_0 KV cache, so every model carries a <strong>128k context</strong> and stays 100 % GPU-resident — the 08-15 local rows were pinned at 64k and Qwen silently lost the front of its prompt. Roster is Blackwell-runnable only: Ollama's <code>nvfp4</code> FP4 builds turn out to be macOS-gated (HTTP 412), so the FP4-vs-Q4 comparison the card invites is not available on Linux yet; <code>qwen3:8b</code> was dropped for spilling to CPU at 128k. Same prompt, harness, and seed state as the five-model 08-15 relay.</p>
<p>Models are grouped by what governs their speed — <strong>active</strong> parameters, not total. A 30B-A3B MoE and a 27B dense model are different questions even though both fit the card.</p>
<div class="legend"><span><i class="sw s-moe"></i>MoE, ~3B active</span><span><i class="sw s-dense"></i>dense</span><span><i class="line-key"></i> Haiku 4.5 reference</span><span><i class="sw crit"></i> no visible answer</span></div>
</div>

<h2>1 · Decode speed is not the bottleneck</h2>
<div class="col"><p>A 400-token generation on an operator-style prompt, best of two, power sampled at 2 Hz. Nine of eleven clear Haiku's 91.9 out tok/s; the MoE lane clears it by ~3×. If a local run is slow end to end, the cause is turns and tool time, not tokens per second.</p></div>
<div class="wide">{bar_chart()}</div>
<details><summary>table view</summary><div class="wide">{probe_table()}</div></details>
<div class="col"><p class="note">The card, not the model, sets the ceiling: <code>qwen38-27b</code> touched the 600 W power limit, and <code>power.max_limit</code> equals the default, so there is no headroom to raise. Peak is a spike; mean W is what the energy column should use.</p></div>

<h2>2 · Speed does not predict diagnosis quality</h2>
<div class="col"><p>Four cases distilled from <code>docs/learnings/</code> — the flee-loop bug given the real <code>choose_action</code> excerpt, the baton saved mid map-transition, the Pewter waypoint five models tuned genomes against, and searching a 1.4 GB log under a 40 KB tool cap. Rubric-scored at temperature 0; a model that spends its whole budget thinking and never answers scores 0 for that case, because on the harness that is a wasted turn.</p></div>
<div class="wide">{scatter()}</div>
<div class="callout"><p><strong>The fastest decoder on the box placed seventh.</strong> <code>laguna-xs</code> (316 tok/s) went silent on two of four cases. <code>qwen3-coder-30b</code> is second on quality, answered everything, and finished the suite in 10.6 s — nine times faster than the model above it. <code>gpt-oss-20b</code> scored 0.00 on the code-reading case by inventing <code>battle_type == 0</code> when the excerpt in its own prompt shows <code>== 1</code>: confident and wrong now ranks below hedged and right.</p></div>
<div class="wide">{eval_table()}</div>

<h2>3 · The relay runs</h2>
<div class="col"><p>Same harness as 08-15: pi + guardrails, the same mission text and <code>route1.state</code> seed, a worktree off the same base commit so every model faces the same repo defects, power sampled at 5 s for the whole run. Goal: <code>route1_to_forest → forest_to_pewter → pewter_to_badge → badge_to_mtmoon</code>. Nobody has reached Mt. Moon yet; the 08-15 field all stalled at Pewter (2/4).</p></div>
{relay_section()}

<div class="col">
<h2>Method &amp; caveats</h2>
<ul>
<li><strong>Decode probe</strong> — <code>scripts/local_models.py bench</code>: <code>/api/generate</code>, 400 tokens, best of two so the load is warm; GPU % is <code>ollama ps</code> <code>size_vram/size</code>. Prompt tok/s on a short prompt is noisy — trust the out tok/s column.</li>
<li><strong>Diagnostic evals</strong> — <code>scripts/run_model_evals.py</code>: regex rubric, not an LLM judge. Rewards saying the true thing, so it is a floor on capability; each learning's own wording is asserted to clear its rubric in the test suite. Read the saved answers before trusting a low score.</li>
<li><strong>Relay run</strong> — <code>scripts/bench_report.py</code> over the pi session transcript; energy from <code>scripts/power_sampler.py</code> integrated over the run. Cloud $ is the same tokens priced at published per-million rates, so local rows are comparable to cloud rows.</li>
<li><strong>Not tested</strong> — Blackwell <code>nvfp4</code> (macOS-only in Ollama's registry), Thinking Machines' Inkling (276B-A12B, ~75 GB smallest quant, cannot stay resident on 32 GB — a cloud row), any OpenRouter model (out of scope).</li>
</ul>
<p class="foot">Data: <code>benchmarks/2026-08-15-local-decode-probe.md</code>, <code>evals/results/models-2026-08-16.md</code>, <code>benchmarks/2026-08-15-mt-moon-relay.md</code>. Roster and tooling: <code>scripts/local_models.py</code>, <code>evals/model-cases/</code>.</p>
</div>
</main>
<script>{JS}</script>
"""


if __name__ == "__main__":
    OUT.write_text(page())
    print(OUT, len(OUT.read_text()), "bytes", "relay:", "final" if RELAY_JSON.exists() else "pending", file=sys.stderr)
