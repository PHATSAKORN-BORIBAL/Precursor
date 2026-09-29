"""Render a sealed incident as a small standalone SVG ("precursor ladder").

Lightweight by design: plain SVG text, no images, a few KB per incident.
"""

from __future__ import annotations

from html import escape
from typing import Mapping

from .narrative import format_t

BG, PANEL, INK, MUTED = "#12202b", "#1a2b38", "#e8eef2", "#8aa0ae"
LEAD, FOLLOW, TRACE, TRIGGER = "#ff6a2b", "#f2c14e", "#5fd0c5", "#ff6a2b"


def render_incident_svg(bundle: Mapping, width: int = 960) -> str:
    p = bundle["payload"]
    an = p["analysis"]
    labels = {c["name"]: c["label"] for c in p["channels"]}
    t = p["t"]
    t0, t1, trig = t[0], t[-1], p["trigger"]["t"]
    left, right, top, row_h = 210, width - 36, 96, 46
    span = max(t1 - t0, 1.0)
    x_of = lambda tt: left + (tt - t0) / span * (right - left)

    moved = [f["channel"] for f in an["chain"]]
    still = [c["name"] for c in p["channels"] if c["name"] not in moved]
    order = moved + still
    height = top + len(order) * row_h + 70
    finding = {f["channel"]: f for f in an["chain"]}
    verdict = an["verdict"]

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
           f'width="{width}" height="{height}" role="img" '
           f'aria-label="Precursor ladder for {escape(p["id"])}">',
           f'<rect width="{width}" height="{height}" fill="{BG}"/>',
           f'<g font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" fill="{INK}">',
           f'<text x="24" y="34" font-size="18" font-weight="700">{escape(p["id"])} '
           f'&#8212; {escape(verdict["label"])} (score {verdict["score"]:.2f})</text>',
           f'<text x="24" y="58" font-size="12" fill="{MUTED}">Triggered {escape(format_t(trig))} on '
           f'{escape(labels.get(p["trigger"]["channel"], ""))} &#183; source: '
           f'{escape(p["provenance"]["source"])} &#183; sealed sha256:{escape(bundle["seal"]["hash"][:12])}</text>']

    for i, name in enumerate(order):
        y = top + i * row_h
        out.append(f'<rect x="{left}" y="{y}" width="{right - left}" height="{row_h - 8}" '
                   f'fill="{PANEL}" rx="3"/>')
        f = finding.get(name)
        dim = "" if f else ' fill-opacity="0.45"'
        arrow = "" if not f else (" &#8593;" if f["direction"] == "up" else " &#8595;")
        out.append(f'<text x="24" y="{y + 22}" font-size="13"{dim}>{escape(labels.get(name, name))}{arrow}</text>')
        if f:
            lead = f["lead_s"]
            note = f"{-lead:.0f}s after trigger" if lead <= 0 else f"{lead:.0f}s before trigger"
            out.append(f'<text x="24" y="{y + 36}" font-size="10" fill="{MUTED}">{escape(note)}</text>')
        zs = p["z"][name]
        pts = []
        mid, amp = y + (row_h - 8) / 2, (row_h - 8) / 2 - 3
        for tt, z in zip(t, zs):
            zc = max(-10.0, min(10.0, z))
            pts.append(f"{x_of(tt):.1f},{mid - zc / 10.0 * amp:.1f}")
        step = max(1, len(pts) // 480)
        out.append(f'<polyline points="{" ".join(pts[::step])}" fill="none" stroke="{TRACE}" '
                   f'stroke-width="1.2" stroke-opacity="{1.0 if f else 0.4}"/>')
        if f:
            colour = LEAD if f["role"] == "precursor" else FOLLOW
            xo, xt = x_of(f["onset_t"]), x_of(trig)
            out.append(f'<rect x="{min(xo, xt):.1f}" y="{y + row_h - 14}" '
                       f'width="{abs(xt - xo):.1f}" height="4" fill="{colour}" rx="2"/>')
            out.append(f'<circle cx="{xo:.1f}" cy="{y + row_h - 12}" r="5" fill="{colour}" '
                       f'stroke="{BG}" stroke-width="2"/>')

    xt = x_of(trig)
    out.append(f'<line x1="{xt:.1f}" y1="{top - 8}" x2="{xt:.1f}" y2="{top + len(order) * row_h - 8}" '
               f'stroke="{TRIGGER}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    out.append(f'<text x="{xt + 6:.1f}" y="{top - 12}" font-size="11" fill="{TRIGGER}">trigger</text>')
    fy = top + len(order) * row_h + 14
    out.append(f'<text x="24" y="{fy}" font-size="11" fill="{MUTED}">Dot = estimated moment the channel left its '
               f'baseline (CUSUM); orange = before the trigger, amber = after. Traces are z-scores clipped to &#177;10.</text>')
    out.append(f'<text x="24" y="{fy + 18}" font-size="11" fill="{MUTED}">Onset order is evidence of '
               f'sequence, not proof of cause. Data shown is {escape(p["provenance"]["source"])} data.</text>')
    out.append("</g></svg>")
    return "\n".join(out)
