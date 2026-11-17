"""Text/HTML report content built from an evaluation Result."""
from __future__ import annotations

import html
import math

import numpy as np

from . import engine
from .common import fmt_len
from .design import FeedChain, Requirements, Spec, l_match
from .engine import Result


def _fz(z: complex) -> str:
    if not np.isfinite(z.real) or not np.isfinite(z.imag):
        return "n/a"
    return f"{z.real:.1f} {'+' if z.imag >= 0 else '-'} j{abs(z.imag):.1f} ohm"


def _swr_cls(s: float) -> str:
    return "good" if s <= 1.5 else "warn" if s <= 2.0 else "bad"


def gain_unit(design) -> str:
    return "dBic" if design.cp else "dBi"


def mass_kg(res: Result) -> float | None:
    d, req = res.design, res.req
    if d.structure is None:
        return None
    L = d.total_wire_m()
    r = req.radius
    area = math.pi * r * r
    if req.hollow_wall_mm > 0:
        wall = min(req.hollow_wall_mm / 1000.0, r * 0.95)
        area = math.pi * (r * r - (r - wall) ** 2)
    return L * area * req.density * 1000.0 + d.mass_extra_kg


def requirement_checks(res: Result, spec: Spec) -> list:
    req, m, d = res.req, res.metrics, res.design
    out = []
    unit = gain_unit(d)
    if req.target_gain is not None:
        g = m["gain_dbi"]
        basis_txt = "over the ground you entered"
        if res.basis == "free" and res.free_gain is not None:
            g = res.free_gain
            basis_txt = "in free space (ground removed)"
        ok = g >= req.target_gain - 0.2
        extra = f"; with your ground it is {m['gain_dbi']:.1f} {unit}" if basis_txt.startswith("in free") else ""
        out.append((f"Gain target {req.target_gain:.1f} {unit}", ok, f"design gives {g:.1f} {unit} {basis_txt}{extra}"))
    if req.max_size > 0:
        if spec.size_fn is not None and res.ex and spec.auto_key:
            sz = spec.size_fn(req, res.ex, res.ex[spec.auto_key])
            ok = sz <= req.max_size * 1.001
            out.append((f"{spec.size_label} {req.max_size:.2f} m", ok, f"design is {sz:.2f} m (longest element {engine.max_extent(d):.2f} m)"))
        else:
            ext = engine.max_extent(d)
            ok = ext <= req.max_size * 1.001
            out.append((f"{spec.size_label} {req.max_size:.2f} m", ok, f"largest dimension {ext:.2f} m"))
    if d.mode == "currents":
        out.append(("Feed network (ideal)", True, "element currents are set by an ideal feed network; port impedances are listed below"))
    elif not d.rx_only:
        if "cm_mode" in m:
            where = "beyond the coax choke" if "cm_i_beyond" in m else "on the coax"
            imax = m.get("cm_i_beyond", m["cm_i_max"])
            out.append((f"Coax common-mode current {where} 20 dB below the feed current", m["cm_ratio_db"] <= -20.0,
                        f"{m['cm_ratio_db']:+.0f} dB ({imax * 1000:.0f} mA rms at most)"))
        rng = m.get("tuner_range") or 0.0
        if rng > 0:
            rtxt = f"{rng:g}:1" if math.isfinite(rng) else "any SWR"
            out.append((f"Tuner can match at the design frequency ({rtxt})", m["swr_f0"] <= rng,
                        f"SWR into the tuner {m['swr_f0']:.2f}:1 at {req.f_mhz:.4g} MHz"))
            if m.get("band_max_swr") is not None and req.f_hi > req.f_lo:
                out.append((f"Tuner can match across the whole band ({rtxt})", m["band_max_swr"] <= rng,
                            f"worst {m['band_max_swr']:.1f}:1 in {req.f_lo:.4g}-{req.f_hi:.4g} MHz"))
        else:
            out.append(("SWR at design frequency 2:1 or better", m["swr_f0"] <= 2.0, f"SWR {m['swr_f0']:.2f}:1 at {req.f_mhz:.4g} MHz"))
            if m.get("band_ok") is not None and req.f_hi > req.f_lo and d.mode != "currents":
                frac = m["band_ok"]
                out.append(("SWR below 2:1 across the whole band", frac >= 0.999,
                            f"{frac * 100:.0f}% of {req.f_lo:.4g}-{req.f_hi:.4g} MHz; worst {m['band_max_swr']:.1f}:1"))

    else:
        out.append(("Receive-only design", True, "judge by directivity and front-to-rear, not gain"))
    return out


def metric_cards(res: Result, spec: Spec) -> list:
    """List of (label, value, tone) for the headline cards."""
    m, d, req = res.metrics, res.design, res.req
    unit = gain_unit(d)
    cards = []
    gain_lbl = "DIRECTIVITY" if d.rx_only else "GAIN"
    gval = m["directivity"] if d.rx_only else m["gain_dbi"]
    cards.append((gain_lbl, f"{gval:.1f} {unit}", "good" if gval > 5 else "text"))
    if m["fb"] is not None:
        cards.append(("FRONT / BACK", f"{m['fb']:.1f} dB", "good" if m["fb"] > 15 else "text"))
    else:
        cards.append(("PATTERN", "omni / bidir.", "text"))
    if d.mode == "currents":
        cards.append(("DRIVEN PORTS", f"{len(res.port_info)}", "text"))
        cards.append(("PORT 1 IMPEDANCE", f"{m['z_ant'].real:.0f} {'+' if m['z_ant'].imag >= 0 else '-'} j{abs(m['z_ant'].imag):.0f}", "text"))
    elif not d.rx_only:
        rng = m.get("tuner_range") or 0.0
        if rng > 0:
            cards.append(("SWR INTO TUNER", f"{m['swr_f0']:.2f} : 1", "good" if m["swr_f0"] <= rng else "bad"))
        else:
            cards.append(("SWR @ F0", f"{m['swr_f0']:.2f} : 1", _swr_cls(m["swr_f0"])))
        cards.append(("BANDWIDTH (SWR<2)", _bw_text(m.get("bw2")), "text"))
    cards.append(("TAKE-OFF ANGLE", f"{m['takeoff']:.0f} deg", "text"))
    cards.append(("EFFICIENCY", f"{m['efficiency'] * 100:.0f} %", "good" if m["efficiency"] > 0.7 else "warn" if m["efficiency"] > 0.3 else "bad"))
    return cards


def _bw_text(bw) -> str:
    if not bw:
        return "none"
    lo, hi, edge = bw
    w = (hi - lo)
    if w >= 1:
        txt = f"{w:.2f} MHz"
    else:
        txt = f"{w * 1000:.0f} kHz"
    return ("> " if edge else "") + txt


def summary_table(res: Result, spec: Spec) -> list:
    m, d, req = res.metrics, res.design, res.req
    unit = gain_unit(d)
    rows = []
    rows.append(("Antenna", d.title))
    rows.append(("Design frequency", f"{req.f_mhz:.4f} MHz  (wavelength {fmt_len(req.lam)})"))
    rows.append((f"Peak gain", f"{m['gain_dbi']:.2f} {unit}  ({m['gain_dbi'] - 2.15:.2f} dBd)"))
    rows.append(("Directivity", f"{m['directivity']:.2f} dBi"))
    rows.append(("Radiation efficiency", f"{m['efficiency'] * 100:.1f} %  (includes wire, load and ground loss)"))
    rows.append(("Polarisation", m["pol"]))
    rows.append(("Take-off angle (peak)", f"{m['takeoff']:.0f} deg above the horizon"))
    rows.append(("Peak azimuth", f"{m['peak_az']:.0f} deg"))
    if m["hpbw_az"]:
        rows.append(("Beamwidth (azimuth, -3 dB)", f"{m['hpbw_az']:.0f} deg"))
    if m["hpbw_el"]:
        rows.append(("Beamwidth (elevation, -3 dB)", f"{m['hpbw_el']:.0f} deg"))
    if m["fb"] is not None:
        rows.append(("Front-to-back", f"{m['fb']:.1f} dB"))
        rows.append(("Front-to-rear (worst)", f"{m['fr']:.1f} dB"))
    rows.append(("Feedpoint impedance (antenna)", _fz(m["z_ant"])))
    if res.port_info and d.mode in ("currents", "equal", "network"):
        for (i, z, ia, ph) in res.port_info:
            rows.append((f"Port {i + 1} impedance (driven)", f"{_fz(z)}   |I| {ia * 1000:.2f} mA/V, phase {ph:+.0f} deg"))
    if d.mode == "currents":
        rows.append(("SWR note", "per-port impedances differ because of mutual coupling; the feed network must match each port"))
    elif not d.rx_only:
        rows.append(("Impedance at the coax input", _fz(m["z_rig"])))
        rows.append((f"SWR on {req.zref:.0f} ohm at {req.f_mhz:.4g} MHz" + (" (into the tuner)" if m.get("tuner_range") else ""),
                     f"{m['swr_f0']:.2f} : 1"))
        if m.get("tuner_range"):
            rng = m["tuner_range"]
            ok = m["swr_f0"] <= rng
            rows.append(("Tuner", ("can match it" if ok else "CANNOT match it")
                         + (f" (range about {rng:g}:1)" if math.isfinite(rng) else " (wide range)")
                         + ("; the transmitter then sees 1:1" if ok else "")))
            if ok:
                tl = m.get("tuner_loss_db", 0.0)
                rows.append(("Tuner loss (estimate)", f"{tl:.2f} dB ({req.power_w * (1 - 10 ** (-tl / 10)):.1f} W at {req.power_w:.0f} W) "
                             f"matching {m['swr_f0']:.1f}:1, inductor Q {m.get('tuner_q', 0):.0f}"))
        for key, lab in (("bw2", "SWR < 2:1 bandwidth"), ("bw15", "SWR < 1.5:1 bandwidth")):
            bw = m.get(key)
            if bw:
                rows.append((lab, f"{bw[0]:.4f} - {bw[1]:.4f} MHz  ({_bw_text(bw)})"))
            else:
                rows.append((lab, "not reached"))
        fc = res.feed
        if fc and fc.line:
            rows.append(("SWR on the feed line", f"{m['swr_line_f0']:.2f} : 1 (line impedance {fc.line[0]:.0f} ohm)"))
            rows.append(("Feed line loss", f"{m['line_loss_db']:.2f} dB at {req.f_mhz:.4g} MHz (including mismatch loss)"))
        bl = engine.balun_loss_db(d, req)
        if bl > 0:
            rows.append(("Balun / transformer loss", f"{m['xfmr_loss_db']:.2f} dB at {req.f_mhz:.4g} MHz (rated {bl:.1f} dB when matched)"))
        rows.append(("Coax loss", f"{m['coax_loss_db']:.2f} dB at {req.f_mhz:.4g} MHz (including mismatch loss)"))
        if "cm_mode" in m:
            rows.append(("Common-mode current on the coax", cm_text(m)))
            if m.get("cm_p_choke", 0) > 0:
                rows.append(("Heat in the balun / choke", f"{m['cm_p_choke']:.1f} W at {req.power_w:.0f} W"))
            if "cm_p_choke2" in m:
                rows.append(("Heat in the coax choke", f"{m['cm_p_choke2']:.1f} W at {req.power_w:.0f} W "
                             f"({m['cm_i_choke2'] * 1000:.0f} mA through it)"))
        elif m.get("cm_skip"):
            rows.append(("Common-mode current on the coax", f"not modelled: {m['cm_skip']}"))
        sl = m.get("sys_loss_db", 0.0)
        frac = 10 ** (-sl / 10) if math.isfinite(sl) else 0.0
        rows.append(("Total feed system loss", f"{sl:.2f} dB: {frac * req.power_w:.0f} W of {req.power_w:.0f} W reaches the antenna, "
                     f"about {frac * m['efficiency'] * req.power_w:.0f} W is radiated"))
        rows.append((f"At {req.power_w:.0f} W: feedpoint current / voltage", f"{m['feed_i']:.2f} A rms / {m['feed_v']:.0f} V rms"))
    mk = mass_kg(res)
    if mk is not None:
        rows.append(("Conductor length (all wires)", f"{d.total_wire_m():.1f} m   weight about {mk:.2f} kg ({req.material})"))
    return rows


def matching_html(res: Result) -> str:
    req, m, d, fc = res.req, res.metrics, res.design, res.feed
    out = ["<h3>Feedpoint and matching</h3>"]
    z = m["z_ant"]
    out.append(f"<p>Impedance at the antenna terminals at {req.f_mhz:.4g} MHz: <b>{_fz(z)}</b>.</p>")
    if m.get("stages"):
        out.append(system_table_html(res))
    out.append(cm_html(res))
    stages = []
    line = fc.line if fc else d.line
    if line:
        stages.append(f"Feeder line {line[0]:.0f} ohm, {line[3]:.2f} m (velocity factor {line[1]:.2f}).")
    if fc and fc.lmatch_enabled and fc.lmatch:
        kind, se, sh = fc.lmatch
        stages.append(_lm_text(kind, se, sh, " (automatic L network, values fixed at the design frequency)"))
    ratio = d.force_ratio or req.ratio
    if ratio != 1.0:
        stages.append(f"Transformer {ratio:g}:1 (antenna side {req.zref * ratio:.0f} ohm to {req.zref:.0f} ohm)"
                      + (f", loss {d.xfmr_loss_db:.1f} dB when matched." if d.xfmr_loss_db > 0 else "."))
    if fc and fc.coax[3] > 0:
        stages.append(f"Coax: {fc.coax[0]:.0f} ohm, {fc.coax[3]:.1f} m, loss {m['coax_loss_db']:.2f} dB.")
    out.append("<ol>" + "".join(f"<li>{s}</li>" for s in stages) + "</ol>" if stages else "<p>Direct connection (no matching network).</p>")
    zl = m["z_feed"]
    out.append(f"<p>Impedance after matching, at the coax: <b>{_fz(zl)}</b> (SWR {m['swr_feed_f0']:.2f}:1 on {req.zref:.0f} ohm).</p>")
    # suggestion for a clean match at this frequency (from the antenna impedance after the feeder)
    zin = z
    if line:
        zin, _ = FeedChain.tline(z, line, req.f_mhz)
    sol = l_match(zin, req.zref * ratio, req.f_mhz)
    if sol and not (fc and fc.lmatch_enabled):
        kind, se, sh = sol
        out.append("<h3>Suggested L-network</h3>")
        where = "at the bottom of the feed line" if line else "at the antenna end"
        out.append(f"<p>A lossless L-network {where} would give a perfect match at the centre frequency: " + _lm_text(kind, se, sh, "") + "</p>")
    rr = z.real
    if rr > 0 and ratio == 1.0:
        out.append(f"<p>Nearest simple transformer: <b>{max(rr / req.zref, req.zref / max(rr, 1e-6)):.1f}:1</b> "
                   f"({'step-down' if rr > req.zref else 'step-up'}) &mdash; but a transformer does not cancel reactance.</p>")
    out.append("<p class='dim'>The automatic L-network is ideal (lossless). The tuner loss is an estimate: the lowest-loss L network for "
               "the impedance the tuner sees, with the inductor Q shown (capacitors Q 1000); a T-network tuner usually loses more, "
               "especially into low impedances. Line losses are calculated at the actual SWR on each line; "
               "the balun / transformer loss is the value you entered (or the antenna model's).</p>")
    return "".join(out)


def cm_text(m: dict) -> str:
    r = m["cm_ratio_db"]
    verdict = ("good" if r <= -30 else "acceptable" if r <= -20 else "high - add or improve a choke")
    if "cm_i_beyond" in m:
        return (f"{m['cm_i_beyond'] * 1000:.0f} mA rms at most beyond the coax choke ({r:+.0f} dB relative to the "
                f"{m['cm_i_feed']:.2f} A feed current: {verdict}); {m['cm_i_max'] * 1000:.0f} mA at most anywhere on the coax, "
                f"{m['cm_i_radio'] * 1000:.0f} mA at the radio")
    return (f"{m['cm_i_max'] * 1000:.0f} mA rms at most ({r:+.0f} dB relative to the {m['cm_i_feed']:.2f} A feed current: {verdict}); "
            f"{m['cm_i_balun'] * 1000:.0f} mA at the balun, {m['cm_i_radio'] * 1000:.0f} mA at the radio")


def cm_html(res: Result) -> str:
    m, req = res.metrics, res.req
    if "cm_mode" not in m:
        if m.get("cm_skip"):
            return f"<h3>Coax common-mode current</h3><p>Not modelled: {html.escape(m['cm_skip'])}.</p>"
        return ""
    how = ("The outside of the coax shield is part of the antenna model, from the balun at the feedpoint to the radio, joined "
           "through the balun's common-mode impedance; the SWR, pattern and gain above include it."
           if m["cm_mode"] == "feedpoint" else
           f"The feed line is assumed balanced, so the coax is driven at the balun by half the voltage across it "
           f"({m.get('cm_v', 0):.0f} V rms), against the feed line and antenna. Common-mode path impedance "
           f"{_fz(m.get('cm_zpath', 0j))} plus the balun's common-mode impedance. This estimate does not change the main result.")
    rows = [("Largest current on the coax", f"{m['cm_i_max'] * 1000:.0f} mA rms"),
            ("At the balun / at the radio", f"{m['cm_i_balun'] * 1000:.0f} mA / {m['cm_i_radio'] * 1000:.0f} mA"),
            ("Feed (differential) current", f"{m['cm_i_feed']:.2f} A rms")]
    if "cm_i_beyond" in m:
        rows += [(f"Through the coax choke ({req.choke2_ohm:.0f} ohm, {req.choke2_dist:g} m down)", f"{m['cm_i_choke2'] * 1000:.0f} mA rms"),
                 ("Largest current beyond the coax choke", f"{m['cm_i_beyond'] * 1000:.0f} mA rms"),
                 ("Beyond the choke, relative to feed", f"{m['cm_ratio_db']:+.1f} dB"),
                 ("Heat in the coax choke", f"{m['cm_p_choke2']:.1f} W at {req.power_w:.0f} W")]
    else:
        rows += [("Common mode relative to feed", f"{m['cm_ratio_db']:+.1f} dB")]
    rows += [("Heat in the balun / choke", f"{m.get('cm_p_choke', 0):.1f} W at {req.power_w:.0f} W")]
    if m.get("cm_note"):
        rows += [("Note", html.escape(m["cm_note"]))]
    tips = ("<p class='dim'>Below about -30 dB is good, -20 to -30 dB is usually fine, above -20 dB the coax is part of the "
            "antenna: RF in the shack, noise pickup and a distorted pattern are likely. A current balun or choke of a few kilohms "
            "(resistive) is the cure; a voltage balun or unun gives little isolation. Heat in the choke shows when it is "
            "working hard - ferrite chokes fail when they run hot.</p>")
    return ("<h3>Coax common-mode current</h3><p>" + how + "</p><table>"
            + "".join(f"<tr><th>{a}</th><td>{b}</td></tr>" for a, b in rows) + "</table>" + tips)


def system_table_html(res: Result) -> str:
    """The whole antenna system, transmitter first, with impedance, SWR and power lost in each part."""
    req, m = res.req, res.metrics
    stages = m.get("stages") or []
    p = req.power_w
    losses = [st[3] for st in stages]
    rows = []
    for k, (name, zz, sw, loss) in enumerate(stages):
        nearer = sum(losses[k + 1:])          # stages between this one and the transmitter
        pin = p * 10 ** (-nearer / 10) if math.isfinite(nearer) else 0.0
        pout = pin * 10 ** (-loss / 10) if math.isfinite(loss) else 0.0
        rows.append(f"<tr><td>{html.escape(name)}</td><td>{_fz(zz)}</td><td>{'' if sw is None else f'{sw:.2f} : 1'}</td>"
                    f"<td>{'' if loss == 0 else f'{loss:.2f} dB'}</td><td>{'' if loss == 0 else f'{pin - pout:.1f} W'}</td></tr>")
    tot = m.get("sys_loss_db", 0.0)
    reach = p * 10 ** (-tot / 10) if math.isfinite(tot) else 0.0
    total = (f"<tr><td colspan='3'><b>Total</b>: {reach:.0f} W of {p:.0f} W reaches the antenna; about "
             f"{reach * m['efficiency']:.0f} W is radiated (antenna efficiency {m['efficiency'] * 100:.0f} %)</td>"
             f"<td><b>{tot:.2f} dB</b></td><td><b>{p - reach:.1f} W</b></td></tr>")
    return (f"<h3>The antenna system as connected, at {req.f_mhz:.4g} MHz</h3>"
            "<p>Transmitter first, antenna last. <i>Impedance</i> is what you would measure at the transmitter end of each part, "
            "looking toward the antenna; <i>SWR on it</i> is relative to that part's own impedance; losses include the extra loss "
            "caused by the SWR on each line.</p>"
            "<table><tr><th>Part</th><th>Impedance</th><th>SWR on it</th><th>Loss</th><th>Power lost</th></tr>"
            + "".join(reversed(rows)) + total + "</table>")


def _lm_text(kind, se, sh, tail):
    def el(e):
        t, v = e
        if t == "L":
            return f"{v * 1e6:.3g} uH" if v >= 1e-7 else f"{v * 1e9:.3g} nH"
        return f"{v * 1e12:.4g} pF"
    ser = f"series {'inductor' if se[0] == 'L' else 'capacitor'} {el(se)}"
    shu = f"shunt {'inductor' if sh[0] == 'L' else 'capacitor'} {el(sh)}"
    if kind == "shunt_first":
        return f"{shu} across the antenna terminals, then {ser} toward the transmitter{tail}"
    return f"{ser} at the antenna, then {shu} toward the transmitter{tail}"


def notes_html(res: Result, spec: Spec) -> str:
    d = res.design
    out = []
    if d.warnings:
        out.append("<h3 style='color:#ffbf5f'>Warnings</h3><ul>" + "".join(f"<li>{html.escape(w)}</li>" for w in d.warnings) + "</ul>")
    out.append("<h3>Design notes</h3><ul>" + "".join(f"<li>{html.escape(n)}</li>" for n in d.notes) + "</ul>")
    if spec.desc:
        out.insert(0, f"<p>{html.escape(spec.desc)}</p>")
    method = ("Closed-form model (analytic formulas)" if d.analytic is not None else
              "Thin-wire method-of-moments simulation (built-in NEC-style solver)")
    if d.analytic is None and res.model is not None:
        out.append(f"<p class='dim'>{method}: {res.model.N} segments, {res.model.M} basis functions; "
                   f"ground: {res.design.structure.ground.kind}.</p>")
    else:
        out.append(f"<p class='dim'>{method}.</p>")
    return "".join(out)


def bands_rows(res: Result) -> list:
    rows = []
    for (label, f, z, swr, g, to) in res.bands:
        rows.append((label, f"{f:.3f}", _fz(z), f"{swr:.2f}" if np.isfinite(swr) else "n/a",
                     f"{g:.1f}" if np.isfinite(g) else "n/a", f"{to:.0f}" if np.isfinite(to) else "n/a"))
    return rows


def full_report_html(res: Result, spec: Spec, images: dict | None = None) -> str:
    css = """<style>
    body { font-family: 'Segoe UI', Arial; font-size: 10pt; color: #111; }
    h1 { color: #1a4a7a; } h2 { color: #1a4a7a; border-bottom: 1px solid #aab; margin-top: 18px; }
    table { border-collapse: collapse; } td, th { border: 1px solid #bbb; padding: 3px 7px; }
    th { background: #e8eef4; text-align: left; } .dim { color: #666; }
    </style>"""
    d, req = res.design, res.req
    parts = [css, f"<h1>AntennaCalc design report</h1><h2>{html.escape(d.title)}</h2>"]
    parts.append("<table>" + "".join(f"<tr><th>{html.escape(a)}</th><td>{html.escape(b)}</td></tr>" for a, b in summary_table(res, spec)) + "</table>")
    chk = requirement_checks(res, spec)
    parts.append("<h2>Requirements check</h2><table>" + "".join(
        f"<tr><td>{'PASS' if ok else 'FAIL'}</td><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, ok, b in chk) + "</table>")
    parts.append("<h2>Dimensions / cut list</h2><table><tr><th>Item</th><th>Qty</th><th>Length</th><th>Note</th></tr>" + "".join(
        f"<tr><td>{html.escape(x.item)}</td><td>{x.qty}</td><td>{html.escape(fmt_len(x.length_m)) if x.length_m else ''}</td><td>{html.escape(x.note)}</td></tr>" for x in d.dims) + "</table>")
    if images:
        for title, b64 in images.items():
            parts.append(f"<h2>{html.escape(title)}</h2><img src='data:image/png;base64,{b64}'/>")
    parts.append(matching_html(res))
    if res.bands:
        parts.append("<h2>Multi-band performance</h2><table><tr><th>Band</th><th>MHz</th><th>Feed impedance</th><th>SWR</th><th>Gain dBi</th><th>Take-off</th></tr>" + "".join(
            "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>" for r in bands_rows(res)) + "</table>")
    parts.append(notes_html(res, spec))
    return "".join(parts)
