"""Plain-language incident write-up and terminal report (rule-based, no LLM)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping


def format_t(t: float) -> str:
    """Unix-like timestamps become UTC ISO strings; small ones become T+HH:MM:SS."""
    if t > 1e9:
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    total = int(round(t))
    return f"T+{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _dur(seconds: float) -> str:
    s = abs(int(round(seconds)))
    return f"{s} s" if s < 120 else f"{s // 60} min {s % 60:02d} s"


def _arrow(direction: str) -> str:
    return "rising" if direction == "up" else "falling"


def build_narrative(trigger: Mapping, chain: list[Mapping], analysis_verdict: Mapping,
                    hypotheses: list[Mapping], labels: Mapping[str, str]) -> str:
    name = lambda c: labels.get(c, c)
    parts = [f"The recorder triggered at {format_t(trigger['t'])} on {name(trigger['channel'])}, "
             f"which had sat {abs(trigger['z']):.1f} standard deviations from its learned baseline "
             f"for several consecutive samples."]
    if not chain:
        parts.append("No channel showed a clear onset inside the recorded window.")
        return " ".join(parts)

    first = chain[0]
    lead = "" if first["lead_s"] <= 0 else f", {_dur(first['lead_s'])} before the trigger"
    clipped = " (it was already moving when the window began, so the true start is earlier)" \
        if first.get("clipped") else ""
    parts.append(f"Looking back through the buffer, the first channel to leave its baseline was "
                 f"{name(first['channel'])} ({_arrow(first['direction'])}){lead}{clipped}.")
    rest = chain[1:]
    if rest:
        seq = "; ".join(f"{name(f['channel'])} ({_arrow(f['direction'])}) "
                        f"{_dur(f['onset_t'] - first['onset_t'])} later" for f in rest[:5])
        parts.append(f"It was followed by {seq}.")

    if analysis_verdict.get("confident") and hypotheses:
        best = hypotheses[0]
        parts.append(f"The observed order best matches the known pattern '{best['title']}' "
                     f"(match score {best['score']:.2f}): {best['summary']}")
        if analysis_verdict.get("ambiguous_with"):
            parts.append("Other patterns score almost as high (" +
                         ", ".join(analysis_verdict["ambiguous_with"]) +
                         "), so treat this as a shortlist rather than a single answer.")
    else:
        parts.append("The observed order does not match any known pattern with enough "
                     "confidence, so it is reported as an unknown pattern. The onset "
                     "order above is still useful evidence for a manual inspection.")
    parts.append("Note: an onset order shows sequence, not proof of cause.")
    return " ".join(parts)


def render_text_report(bundle: Mapping, width: int = 60) -> str:
    """ASCII report used by the CLI: header, onset ladder, hypotheses, checks."""
    p = bundle["payload"]
    seal = bundle["seal"]
    labels = {c["name"]: c["label"] for c in p["channels"]}
    an = p["analysis"]
    verdict = an["verdict"]
    trig_t = p["trigger"]["t"]
    lines = ["=" * 78,
             f" {p['id']}  |  {p['machine']['name']}  |  source: {p['provenance']['source']}",
             "=" * 78,
             f" Trigger : {format_t(trig_t)} on {labels.get(p['trigger']['channel'])} "
             f"(z = {p['trigger']['z']:+.1f})",
             f" Window  : {format_t(p['window']['start_t'])} .. {format_t(p['window']['end_t'])} "
             f"({p['window']['sample_count']} samples)",
             f" Verdict : {verdict['label']}  (score {verdict['score']:.2f}, "
             f"{'confident' if verdict['confident'] else 'NOT confident'})",
             "", " Precursor ladder (who moved first), time relative to trigger:"]
    chain = an["chain"]
    if chain:
        lo = min(f["onset_t"] for f in chain) - trig_t
        hi = max(0.0, max(f["onset_t"] for f in chain) - trig_t)
        span = max(hi - lo, 1.0)
        for f in chain:
            rel = f["onset_t"] - trig_t
            pos = int((rel - lo) / span * (width - 1))
            trig_pos = int((0 - lo) / span * (width - 1))
            bar = [" "] * width
            for i in range(min(pos, trig_pos), max(pos, trig_pos) + 1):
                bar[i] = "-"
            bar[pos] = "o"
            if 0 <= trig_pos < width:
                bar[trig_pos] = "|" if bar[trig_pos] == " " else bar[trig_pos]
            arrow = "^" if f["direction"] == "up" else "v"
            lines.append(f"  {labels.get(f['channel'], f['channel']):<20.20} {arrow} "
                         f"{''.join(bar)} {rel:+6.0f}s")
        lines.append(f"  {'':<23}{' ' * max(0, int((0 - lo) / span * (width - 1)))}"
                     f"^ trigger")
    else:
        lines.append("  (no channel showed a clear onset)")
    lines += ["", " Pattern matches (heuristic, higher is better):"]
    for h in an["hypotheses"][:4]:
        filled = int(round(h["score"] * 20))
        lines.append(f"  {h['fault']:<20} [{'#' * filled}{'.' * (20 - filled)}] {h['score']:.2f}")
    if verdict["confident"]:
        best = an["hypotheses"][0]
        lines += ["", " Suggested checks:"] + [f"  - {c}" for c in best["checks"]]
    lines += ["", " Narrative:"] + _wrap(p["narrative"], 76, "  ")
    lines += ["", f" Seal: {seal['algo']}:{seal['hash'][:16]}...  (prev {seal['prev_hash'][:8]}...)", "=" * 78]
    return "\n".join(lines)


def _wrap(text: str, width: int, indent: str) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent)
