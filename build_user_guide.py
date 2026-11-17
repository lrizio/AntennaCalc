#!/usr/bin/env python3
"""Generates build/AntennaCalc User Guide.pdf -- the end-user guide for AntennaCalc.

Same structure and styling as the other HamProjects guides.  Screenshots come from docs/guide/, rendered by
scripts/guide_screens.py.   Usage (from the project root):   python build_user_guide.py
Requires (build-time only): pip install reportlab pillow
"""
from __future__ import annotations

import os

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (CondPageBreak, Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from antennacalc import VERSION, models  # noqa: F401
from antennacalc.design import CATEGORIES, REGISTRY

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(ROOT, "build", "AntennaCalc User Guide.pdf")
SHOTS = os.path.join(ROOT, "docs", "guide")

ACCENT = colors.HexColor("#1565c0")
CALLOUT_BG = colors.HexColor("#fff3e0")
CALLOUT_BORDER = colors.HexColor("#e0a030")
NOTE_BG = colors.HexColor("#e8f0fe")
NOTE_BORDER = colors.HexColor("#8ab4f8")
TABLE_HEADER_BG = colors.HexColor("#eeeeee")
MUTED = colors.HexColor("#555555")
CONTENT_W = 7.2 * inch

styles = getSampleStyleSheet()
style_title = ParagraphStyle("GuideTitle", parent=styles["Title"], fontSize=26, leading=30, spaceAfter=2)
style_subtitle = ParagraphStyle("GuideSubtitle", parent=styles["Normal"], fontSize=11, leading=14, textColor=MUTED,
                                alignment=TA_CENTER, spaceAfter=14)
style_body = ParagraphStyle("GuideBody", parent=styles["Normal"], fontSize=10, leading=13, spaceAfter=5)
style_h1 = ParagraphStyle("GuideH1", parent=styles["Heading1"], fontSize=16, leading=19, textColor=ACCENT,
                          spaceBefore=6, spaceAfter=6)
style_h2 = ParagraphStyle("GuideH2", parent=styles["Heading2"], fontSize=12.5, leading=14, textColor=ACCENT,
                          spaceBefore=8, spaceAfter=3)
style_h3 = ParagraphStyle("GuideH3", parent=styles["Heading3"], fontSize=10.5, leading=13,
                          textColor=colors.HexColor("#333333"), spaceBefore=5, spaceAfter=2)
style_bullet = ParagraphStyle("GuideBullet", parent=styles["Normal"], fontSize=9.5, leading=12)
style_cell = ParagraphStyle("GuideCell", parent=styles["Normal"], fontSize=8.5, leading=10.5)
style_cell_b = ParagraphStyle("GuideCellB", parent=style_cell, fontName="Helvetica-Bold")
style_caption = ParagraphStyle("GuideCaption", parent=styles["Normal"], fontSize=8.5, leading=10.5,
                               textColor=MUTED, alignment=TA_CENTER, spaceAfter=8)


def P(t, st=style_body):
    return Paragraph(t, st)


def bullets(items):
    return ListFlowable([ListItem(P(i, style_bullet), leftIndent=12) for i in items], bulletType="bullet",
                        leftIndent=14, bulletFontSize=7)


def numbered(items):
    return ListFlowable([ListItem(P(i, style_bullet), leftIndent=12) for i in items], bulletType="1",
                        leftIndent=16, bulletFontSize=9)


def callout(text, kind="tip"):
    bg, br = (CALLOUT_BG, CALLOUT_BORDER) if kind == "warn" else (NOTE_BG, NOTE_BORDER)
    t = Table([[P(text, style_bullet)]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.8, br),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def table(rows, widths, header=True):
    data = [[P(c, style_cell_b if (header and r == 0) else style_cell) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG))
    t.setStyle(TableStyle(st))
    return t


def block(*flow):
    # flatten nested KeepTogethers (e.g. a shot()): reportlab mis-measures them and pushes the whole block to the
    # next page, which left a heading alone on an otherwise blank page
    out = []
    for f in flow:
        out += f._content if isinstance(f, KeepTogether) else [f]
    return KeepTogether(out)


def shot(name, caption, width=CONTENT_W):
    path = os.path.join(SHOTS, name)
    if not os.path.exists(path):
        return P(f"<i>[missing screenshot {name} - run scripts/guide_screens.py]</i>", style_caption)
    w, h = PILImage.open(path).size
    img = Image(path, width=width, height=width * h / w)
    return KeepTogether([img, P(caption, style_caption)])


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.65 * inch, 0.45 * inch, f"AntennaCalc v{VERSION} - User Guide")
    canvas.drawRightString(LETTER[0] - 0.65 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    doc = SimpleDocTemplate(OUT_PATH, pagesize=LETTER, leftMargin=0.65 * inch, rightMargin=0.65 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.7 * inch, title="AntennaCalc User Guide",
                            author="HamProjects")
    s = []
    # ------------------------------------------------------------------ title
    s += [Spacer(1, 0.3 * inch), P("AntennaCalc", style_title),
          P(f"Amateur radio antenna design and simulation &nbsp;|&nbsp; version {VERSION}", style_subtitle)]
    s.append(P("AntennaCalc designs an antenna to <b>your</b> requirements. You choose the antenna type from a drop-down, "
               "then the band, a gain target, a size limit, the conductor material and size, the height and the ground. "
               "It returns the dimensions (a cut list), the expected gain and patterns, the SWR across the band, the "
               "matching network, and notes on building and tuning it."))
    s.append(shot("01_main.png", "The AntennaCalc window: design inputs on the left, results on the right.", width=5.6 * inch))
    s.append(P("What it can do", style_h2))
    s.append(bullets([
        f"<b>{len(REGISTRY)} antenna designs</b> in {len(CATEGORIES)} categories - wires, verticals, beams, compact and loaded antennas, "
        "VHF/UHF/satellite, microwave and receive-only. Several entries cover more than one named type (for example Dipole / Inverted-V / Sloper), "
        "so every common amateur-radio antenna is available.",
        "<b>Real simulation for wire antennas</b>: a built-in thin-wire moment-method solver gives the true feedpoint impedance, SWR sweep, gain, "
        "patterns, efficiency and ground effects for your exact dimensions, materials and height.",
        "<b>Gain target and size limit</b>: beams choose their own number of elements to reach the gain within your boom limit.",
        "<b>Auto-tune and optimise</b>: dimensions are trimmed to resonance automatically; beams can also be optimised for gain and front-to-back ratio.",
        "<b>Wire Editor</b>: draw your own wire antenna, label and dimension the wires, put sources and loads anywhere on them, "
        "and simulate it like any built-in design (section 5).",
        "<b>Practical outputs</b>: cut list in metres and feet/inches, weight, matching network values, multi-band performance table, NEC-2 export and a PDF report."]))
    s.append(P("Quick start", style_h2))
    s.append(numbered([
        "Pick a <b>Category</b> and an <b>Antenna type</b> at the top of the left panel.",
        "Choose the <b>Band</b> (or edit the design frequency and band edges).",
        "Optionally tick <b>Target gain</b> and/or <b>Size limit</b>.",
        "Choose the <b>Material</b> and <b>conductor diameter</b>, the <b>height</b> and the <b>ground</b>.",
        "Adjust the feed system (transformer, coax) and any <b>Antenna options</b> that appear for this type.",
        "Press <b>DESIGN</b> (F5). Results appear in the tabs on the right when the calculation finishes (a few seconds; large arrays take longer)."]))
    s.append(P("To design an antenna that is not in the list, draw it on the <b>Wire Editor</b> tab (Ctrl+E) - see section 5."))
    s.append(PageBreak())

    # ------------------------------------------------------------------ the window
    s.append(P("1. The window", style_h1))
    s.append(P("The left panel holds your requirements. The right side shows four-to-six headline cards (gain or directivity, front-to-back, SWR, "
               "bandwidth, take-off angle, efficiency) above nine result tabs: <b>Summary, Dimensions, Patterns, SWR / Impedance, Geometry, 3D Pattern, Matching, Multi-band</b> and <b>Notes</b>, followed by the <b>Wire Editor</b> tab for drawing your own antenna (section 5)."))
    s.append(shot("12_inputs.png", "The design input panel.", width=2.6 * inch))
    s.append(table([
        ["Input", "What it does"],
        ["Category / Antenna type", "Selects the design. A one-line description appears below. Changing the type resets height, ground, band and feed settings to sensible defaults for that antenna."],
        ["Band, Design frequency, Band start / end", "The band list sets all three. Edit them to design for any frequency; the band edges drive the SWR check and bandwidth figures. 'Custom range' is for wideband antennas (LPDA, discone)."],
        ["Target gain", "Gain you want in dBi (dBic for circular antennas). Beams, collinears, helix, slot arrays, dishes and horns size themselves to reach it. Choose whether the target means free-space gain (recommended) or gain including ground reflection."],
        ["Size limit", "Largest dimension you can accept - boom length for beams, span for wire antennas, height for verticals, diameter for dishes and loops. The label under the field shows what is limited for the current antenna."],
        ["Material", "Copper, copper-clad steel, aluminium, brass, stainless steel and others. The conductivity sets the loss; the density sets the weight."],
        ["Conductor diameter", "AWG wire sizes, tube sizes and metric sizes, or a custom value. Thicker conductors widen the bandwidth and shift resonant lengths. 'Hollow tube' reduces the weight estimate."],
        ["Height above ground, Ground", "Height of the antenna (or lowest wire / feedpoint, depending on type). Ground types run from free space to salt water. Perfect ground is the ideal reflector."],
        ["Transmit power", "Used for the current and voltage at the feedpoint."],
        ["Feed line, Feed line length", "The line from the antenna down to the balun: 450 ohm ladder line, 300 ohm twin-lead, 600 ohm open wire or any coax. "
         "'Antenna's own' keeps the feeder an antenna type defines (doublet / G5RV, Zepp) and is none for the others; 'None' puts the balun at the feedpoint."],
        ["Balun / unun, Ratio", "What joins the feed line (or the antenna) to the coax, and its impedance ratio, chosen separately - so a 9:1 "
         "<i>balun</i> onto ladder line and a 9:1 <i>unun</i> on an end-fed wire are both possible. A <b>current balun / choke</b> blocks "
         "common-mode current on the coax; a <b>voltage balun</b> blocks little; an <b>unun</b> (or coax straight on, 1:1) blocks none - right for "
         "end-fed antennas, wrong onto ladder line or a dipole. End-fed antennas and verticals default to unun, the others to current balun."],
        ["Balun loss", "Its loss when matched; modelled as core loss, so it grows when the balun sees a high impedance (as real baluns do)."],
        ["Choke impedance", "Common-mode impedance of the current balun or choke (500-1000 ohm for a few ferrite beads, 2-5 kohm for a good "
         "toroid choke, 5-10 kohm or more for a well-designed one)."],
        ["Estimate coax common-mode current, grounded at the radio", "Adds the outside of the coax shield to the model and reports the current "
         "on it and the heat in the choke - see 'Common-mode current on the coax' in section 4."],
        ["Coax runs toward, Coax run height, Feed line comes down to", "Where the feed system runs: the direction of the coax toward the radio "
         "(degrees from the X axis toward Y, as on the Geometry tab; 'auto' is at right angles to the antenna), the height of its horizontal run, "
         "and the height a feed line comes down to before it turns toward the radio (the balun is at its end). The Geometry tab draws the result, "
         "and the coax common-mode estimate uses the same route."],
        ["Extra coax choke, Choke distance from balun", "A second common-mode choke on the coax, besides the balun, at a distance down the "
         "coax from the balun - for example a few metres down an EFHW's coax so the top of the coax is the counterpoise, or where the coax "
         "enters the shack. Results then report the current beyond the choke (what reaches the shack) and the heat in it."],
        ["Coax to radio, Coax length", "The coax from the balun to the transmitter."],
        ["Tuner at radio, Tuner inductor Q", "An antenna tuner at the transmitter: the rig's internal ATU (about 3:1), an external ATU (about 10:1) or a wide-range / balanced tuner. "
         "With a tuner the SWR checks become 'can the tuner match it', and its loss is estimated for the impedance it actually sees. "
         "The internal ATU and the balanced tuner are modelled as L networks; the external ATU as a high-pass T network (C-L-C, 250 pF capacitors) "
         "at its lowest-loss setting. The loss comes from the inductor Q: leave it at 'typical' (60 internal, 120 external, 150 balanced) or enter your tuner's."],
        ["System impedance", "The transmitter impedance, normally 50 ohm."],
        ["Automatic L-match", "Adds an ideal L-network at the feedpoint (or at the bottom of the feed line), calculated at the design frequency, so the antenna is matched to your system impedance. The values appear on the Matching tab."],
        ["Antenna options", "Settings special to the chosen design (number of radials, element count, traps, termination resistor, windings sense, and so on)."],
        ["Calculation", "Fast / Normal / Fine controls the number of wire segments per wavelength. Auto-tune trims lengths to resonance; Optimise (beams) refines spacings and lengths. "
         "<b>Scan a frequency range</b> (HF wire antennas and verticals) plots SWR and impedance between a Start and Stop frequency you choose (default 1.8 to 55 MHz) with the amateur bands shaded, "
         "so harmonic and multi-band behaviour is visible; it is on by default for the EFHW and takes a few seconds longer. On the SWR / Impedance tab, <b>click the graph</b> to read the SWR, impedance, gain and take-off angle at that frequency."]],
        [1.9 * inch, 5.3 * inch]))
    s.append(Spacer(1, 6))
    s.append(callout("<b>Tip:</b> change one thing at a time and press DESIGN again; most designs finish in a second or two. "
                     "The first run of a heavier array (rhombic, discone, helix) can take 10-30 seconds - the progress bar shows what it is doing and Cancel stops it."))
    s.append(PageBreak())

    # ------------------------------------------------------------------ gain target
    s.append(P("2. Designing to a gain target and size limit", style_h1))
    s.append(P("For antennas whose gain depends on size, AntennaCalc searches for the smallest design that meets your target within your limit. "
               "In the example below a 20 m Yagi was requested with at least 11 dBi (free space) and a boom limit of 18 m."))
    s.append(shot("02_yagi_summary.png", "Summary tab: the requirement checks come first (PASS / FAIL), then every key figure.", width=6.4 * inch))
    s.append(P("Reading the requirement checks", style_h3))
    s.append(bullets([
        "<b>Gain target</b> - compares the designed gain with your target. With 'free-space' selected the design is also simulated with the ground removed, so a high antenna over good ground does not hide a design that is too small.",
        "<b>Size limit</b> - for beams the boom length is compared with your limit; the longest element is shown for information.",
        "<b>SWR</b> - the SWR at the design frequency, and the percentage of the band edge to edge with SWR below 2:1.",
        "If the target cannot be reached within the limit, the closest design is shown, the check fails, and a note explains why."]))
    s.append(callout("<b>Gain figures:</b> dBi is gain over an isotropic radiator; dBd = dBi - 2.15. Gain over real ground includes the ground reflection, "
                     "which can add up to 5-6 dB for a horizontal antenna at a good height - that is why the free-space option exists.", "tip"))
    s.append(PageBreak())

    # ------------------------------------------------------------------ results tabs
    s.append(P("3. The result tabs", style_h1))
    def sec(title, text, name, caption, width=4.9 * inch):
        s.append(block(P(title, style_h2), P(text), shot(name, caption, width=width)))
    sec("Dimensions", "The cut list gives each wire, element or part with quantity, length in metres and in feet/inches, and a note. The line under the table gives the total "
        "conductor length and the estimated weight for the material you chose. Export it with <b>Export cut list (CSV)</b> or copy it to the clipboard.",
        "06_dimensions.png", "Dimensions tab for the Yagi.")
    sec("Patterns", "An azimuth cut (compass bearing, north at the top - the model's boom or main direction points north) at the peak take-off angle, and an elevation cut through the "
        "peak. The elevation plot shows the horizon at left and right and the ground below. Choose the polarisation component (total, vertical, horizontal, right-hand or left-hand circular), "
        "overlay the others, and select a 20 to 60 dB scale. Hover over a plot to read any angle.",
        "03_patterns.png", "Patterns tab: azimuth and elevation cuts of the 20 m Yagi.")
    sec("SWR / Impedance", "The SWR curve (log scale) and feedpoint resistance and reactance across the band, with your band edges shaded and the 2:1 and 1.5:1 lines marked. "
        "Choose where SWR is measured: at the coax input (what the transmitter sees, including coax loss), at the feedpoint after matching, or on the feeder line "
        "(for ladder-line fed antennas). <b>Export sweep (CSV)</b> saves the numbers.", "04_swr.png", "SWR / Impedance tab.")
    sec("Geometry", "A rotatable 3-D view of the simulated wires: drag to rotate, wheel to zoom, double-click to reset, with Isometric / Top / Side / Front buttons. "
        "Red dots are feedpoints, amber squares are loads (traps, coils, resistors). The grid shows the ground when one is modelled. "
        "The feed system is drawn too, as it is set on the input panel: the feed line (dashed), the balun or unun (blue square), the coax (grey) "
        "with any extra choke (green ring), the radio and tuner, and the ground symbol where the coax is grounded.", "05_geometry.png", "Geometry tab.")
    sec("3D Pattern", "The radiation pattern as a shaded solid: the distance from the centre and the colour both show gain (the colour bar gives the scale, set by the same dB-scale box as the Patterns tab). "
        "Drag to rotate, wheel to zoom, and use the Oblique / Top / Side / Front buttons. The antenna itself is drawn inside the pattern (tick or untick <i>show antenna in the pattern</i>), so you can see which way each lobe points relative to the elements. The ring on the floor marks the horizon and N / E / S / W show the compass directions.",
        "05b_surface.png", "3D Pattern tab: a 3-element Yagi over ground.")
    sec("Matching", "Describes the whole feed system. The table <i>The antenna system as connected</i> lists every part from the transmitter to the antenna "
        "with the impedance at its transmitter end, the SWR on it, its loss and the watts it turns into heat, then the power that reaches the antenna "
        "and the power radiated. Below it: the impedance after matching, and a suggested "
        "lossless L-network that gives a perfect match at the design frequency (component values in uH and pF). It also shows the nearest simple transformer ratio.",
        "07_matching.png", "Matching tab for an off-centre-fed dipole.")
    sec("Multi-band", "For multi-band antennas (OCFD, G5RV, fan and trap dipoles, EFHW, long wires, trap verticals) the antenna is evaluated at every band it can serve using the same "
        "dimensions: feed impedance, SWR, peak gain and take-off angle. Bands with SWR above 2:1 are marked in red; those usually need an antenna tuner.",
        "08_multiband.png", "Multi-band tab.")
    s.append(P("Notes", style_h2))
    s.append(P("Warnings (for example a conductor that is thick compared with the wavelength, or a size limit that was exceeded) and design notes with build and tuning advice."))
    s.append(PageBreak())

    # ------------------------------------------------------------------ examples
    s.append(P("4. Worked examples", style_h1))
    s.append(P("A 40 m and 20 m trap dipole", style_h2))
    s.append(P("Select <i>HF wire antennas - Trap dipole</i>, set the band to 20 m, then in <b>Antenna options</b> choose 40 m as the second (lower) band. "
               "AntennaCalc sizes each section, designs the traps (the capacitor value is yours to choose, the coil value follows) and tunes both bands. "
               "The Dimensions tab lists the section lengths and trap L and C; the Multi-band tab shows how it works on 40 m and 20 m."))
    s.append(shot("11b_trap_dims.png", "Trap dipole cut list with trap coil and capacitor values.", width=5.0 * inch))
    s.append(P("A wideband log-periodic array", style_h2))
    s.append(P("Select <i>Directional beams - Log-periodic dipole array (LPDA)</i>. The band switches to a custom range (14 to 30 MHz by default; edit the band start and end). "
               "The number of elements, element lengths, spacings and the boom-line impedance are worked out from the bandwidth. The pattern and the SWR across the whole range follow."))
    s.append(shot("09_lpda.png", "LPDA pattern over the 14 to 30 MHz range (13 elements).", width=5.0 * inch))
    s.append(P("A dish for a 13 cm link", style_h2))
    s.append(P("Select <i>Microwave antennas - Parabolic dish</i>, band 13 cm, and enter a target gain. The dish diameter, focal length, depth and the feed illumination angle follow from the gain and the f/D ratio and aperture efficiency you set."))
    s.append(shot("10_dish.png", "Dish pattern for a 28 dBi target.", width=5.0 * inch))
    s.append(P("Wire arrays: Bobtail, Bruce, Sterba and W8JK", style_h2))
    s.append(P("Four arrays that get gain from phasing a few wires rather than from a boom. All are single-band; set the band first, then the options. "
               "Each array has a <b>direction</b> setting: it is the compass bearing of the main lobe (broadside to the wires for the curtains and the Bruce array, along the line joining the elements for the W8JK). "
               "Bidirectional arrays have a second lobe on the opposite bearing."))
    s.append(P("Half-square / Bobtail curtain (Directional beams)", style_h3))
    s.append(P("Quarter-wave verticals hung from half-wave top wires: two verticals for the half-square, three for the Bobtail. The array is fed at the base of one vertical against a radial system "
               "(set the number of radials in <b>Antenna options</b>); the other lower ends are open and held at the <i>lower-end height</i>. The feed point is a voltage maximum, so expect several kilohms "
               "(about 5.5 k&Omega; for the 40 m Bobtail) - the matching L-network is switched on by default. The 40 m Bobtail below gives 4.3 dBi at a 22 degree take-off, about 3.6 dB more than a single "
               "ground-mounted vertical with the same radials; the half-square is about 0.8 dB lower."))
    s.append(shot("13_bobtail_patterns.png", "Bobtail curtain on 40 m: two broadside lobes (north and south) at a low take-off angle.", width=4.8 * inch))
    s.append(shot("13b_bobtail_geo.png", "Geometry: three verticals, the top wire, and the feed (red) at the base of the centre vertical.", width=4.4 * inch))
    s.append(P("Bruce array (Directional beams)", style_h3))
    s.append(P("One continuous wire folded into quarter-wave vertical and horizontal runs, end-fed against ground. The number of vertical sections (2 to 14) sets the gain, "
               "and with a gain target and a width limit the program chooses it for you. Six sections on 40 m give about 6.6 dBi, bidirectional and broadside, with a feed resistance of a few hundred ohms "
               "(the default 4:1 transformer brings it near 50 ohm). In a long end-fed Bruce the current falls toward the far end, so the two lobes become unequal."))
    s.append(shot("14_bruce_patterns.png", "Six-section Bruce array on 40 m.", width=4.8 * inch))
    s.append(shot("14b_bruce_geo.png", "Geometry: the folded wire, fed at the base of the first vertical.", width=4.4 * inch))
    s.append(P("Sterba curtain (HF wire antennas)", style_h3))
    s.append(P("Two rows, half a wavelength apart, of in-phase half-wave sections. Choose the number of sections per row (2 to 10; the program can pick it from a gain target) and, optionally, "
               "a reflector curtain a quarter wavelength behind, which makes the pattern a single lobe. The example is a 4 x 2 curtain with reflector on 20 m at 10 m: 17.7 dBi at an 18 degree take-off, "
               "about 10 dB front-to-back. The rows are driven by ideal in-phase sources, so the impedance shown is the parallel combination; a real curtain is fed through half-wave open-wire phasing lines "
               "and shows several hundred ohms (see the notes). Height is that of the lower row."))
    s.append(shot("15_sterba_patterns.png", "Sterba curtain, 4 x 2 sections with reflector, 20 m.", width=4.8 * inch))
    s.append(shot("15b_sterba_geo.png", "Geometry: two rows of collinear sections, with the unfed reflector row behind.", width=4.4 * inch))
    s.append(P("W8JK flat-top (Directional beams)", style_h3))
    s.append(P("Two parallel horizontal dipoles fed out of phase: bidirectional end-fire along the line that joins them (north and south in the picture; the wires run east-west). "
               "<b>Element spacing</b> (default 1/8 wavelength) and <b>element length</b> (0.5 to 0.7 wavelength) are the options. The feed point is only a few ohms at 1/8 wavelength spacing and rises "
               "toward a quarter wavelength, so a matching network is needed. On 20 m at 12 m high the default gives 9.8 dBi, about 2 dB over a dipole at the same height, with the lobes along the spacing direction."))
    s.append(shot("16_w8jk_patterns.png", "W8JK flat-top on 20 m at 12 m height.", width=4.8 * inch))
    s.append(shot("16b_w8jk_geo.png", "Geometry: two parallel dipoles, each with its own feed point (fed together, out of phase).", width=4.4 * inch))
    s.append(P("End-fed half-wave on several bands (HF wire antennas)", style_h2))
    s.append(P("An EFHW cut for 80 m also resonates near its harmonics, so one wire can serve 80, 40, 20, 15 and 10 m through a 49:1 transformer. "
               "AntennaCalc scans a wide frequency range (the amateur bands are shaded) so you can see the evenly spaced dips, and offers these options:"))
    s.append(bullets([
        "<b>Tune the length for</b> - <i>All harmonic bands</i> (the default) lengthens the wire slightly so the 40/20/15/10 m dips fall on the bands, "
        "at the cost of the 80 m dip sitting a little low; <i>Fundamental band only</i> centres the lowest band and leaves the harmonics a few percent high.",
        "<b>Counterpoise</b> - length and direction of the return wire (the coax shield or a short wire). Hanging it down or away keeps the dips evenly spaced; "
        "in line with the radiator turns the antenna into an off-centre-fed dipole on the higher bands.",
        "<b>Transformer loss</b> - core loss of the 49:1 unun (default 0.5 dB when matched). It is what holds the SWR peaks between the dips to roughly 5-14:1 "
        "instead of 20 or more, and it costs a little transmit power at resonance.",
        "<b>Scan a frequency range</b> - the Calculation-section tick box, on by default for this antenna; untick for the usual band-only sweep (faster). "
        "The same box is available on dipoles, OCFD, G5RV, fan and trap dipoles, long wires, Zepp, loops, Lazy-H, the delta loop and the HF verticals."]))
    s.append(shot("17_efhw_swr.png", "80 m EFHW: SWR from 3 to 30 MHz with the amateur bands shaded.", width=5.0 * inch))
    s.append(shot("17b_efhw_bands.png", "The Multi-band tab for the same wire.", width=5.0 * inch))
    s.append(P("Delta loop with selectable orientation (HF wire antennas)", style_h2))
    s.append(P("A full-wave triangular loop. Choose the <b>orientation</b>: apex up (base at the bottom), apex down (base on top) or horizontal (flat). "
               "<b>Feed point</b> (middle of the base, a corner, or the middle of a slanted side) sets the polarisation, <b>tilt</b> leans a vertical loop over, "
               "and <b>direction</b> is the compass bearing of the broadside lobe. The height setting is the lowest point of the loop."))
    s.append(table([
        ["Choice", "Effect (20 m, 8 m high, average ground)"],
        ["Apex up, feed in the base", "Horizontal polarisation, about 7 dBi at 28 degrees, feed about 120 ohm."],
        ["Apex down, feed in the base", "About 1 dB more gain than apex up and a lower take-off angle (22 degrees)."],
        ["Corner or side feed", "Mixed polarisation with a vertical component; 3-4 dB less peak (horizontal) gain."],
        ["Horizontal", "High-angle (NVIS-type) radiation, about 40 degrees take-off."]],
        [2.2 * inch, 5.0 * inch]))
    s.append(shot("18_delta_patterns.png", "Apex-up delta loop on 20 m: two broadside lobes.", width=4.8 * inch))
    s.append(shot("18b_delta_geo.png", "Geometry, apex up.", width=3.8 * inch))
    s.append(shot("18c_delta_down_geo.png", "Geometry, apex down.", width=3.8 * inch))

    s.append(P("A complete station: doublet, ladder line, 9:1 balun, coax and tuner", style_h2))
    s.append(P("The feed system section of the input panel describes the station as it is actually wired, from the antenna to the transmitter. "
               "Here a 2 x 20 m doublet at 10 m height is used on 40 m, where it is close to a full wavelength and its feedpoint impedance is "
               "about 5000 ohm. It is drawn on the Wire Editor (section 5) and fed with 20 m of 450 ohm ladder line, a 9:1 balun, 10 m of RG-213 "
               "and an external ATU."))
    pics = Table([[shot("20_feed_panel.png", "The feed system settings.", width=2.4 * inch)._content,
                   shot("20b_feed_system.png", "Matching tab: the system as connected, transmitter first.", width=4.6 * inch)._content]],
                 colWidths=[2.6 * inch, 4.6 * inch])
    pics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    s.append(pics)
    s.append(shot("20c_feed_geometry.png", "Geometry tab: the doublet with its ladder line coming down to the 9:1 balun, and the coax running "
                  "on to the radio and tuner.", width=4.6 * inch))
    s.append(table([
        ["Feed system at 7.1 MHz", "SWR into the tuner", "Tuner loss", "Loss, transmitter to antenna"],
        ["30 m of RG-213 straight to the feedpoint, wide-range tuner", "11.4 : 1", "0.17 dB", "10.1 dB (90 W of 100 W lost)"],
        ["20 m ladder line, ideal 9:1 balun, 10 m RG-213, external ATU", "9.0 : 1", "0.27 dB", "1.6 dB (31 W lost)"],
        ["the same with a 0.3 dB (when matched) 9:1 balun", "5.5 : 1", "0.23 dB", "3.7 dB (57 W lost, most of it in the balun)"],
        ["20 m ladder line, ideal 4:1 balun, 10 m RG-213, external ATU", "15.5 : 1", "-", "beyond the ATU's range: it cannot match"]],
        [3.0 * inch, 1.2 * inch, 0.8 * inch, 2.2 * inch]))
    s.append(bullets([
        "Ladder line loses very little even at an SWR of 12:1, while coax at the same SWR throws most of the power away: keep the high-SWR run in ladder line.",
        "A lossy balun <i>lowers</i> the SWR the tuner sees - the loss hides the mismatch - while costing power. A better SWR is not always a better system; read the loss column.",
        "Try different ladder line lengths: the impedance at the bottom of the line, and so the SWR into the tuner and the balun loss, change a lot with length.",
        "Tuner loss depends on the impedance the tuner sees, not only on the SWR. A T-network tuner loses most into <i>low</i> impedances "
        "on the low bands (for example 1.6 dB matching 5 ohm at 3.6 MHz with a Q-120 coil, against 0.1 dB for an L network); into high "
        "impedances it does about as well as an L network. Changing the ladder line length moves the impedance - and the tuner loss.",
        "The SWR / Impedance tab can show the SWR at the coax input (into the tuner), after the balun, or on the feed line itself."]))

    s.append(P("Common-mode current on the coax: balun or unun?", style_h2))
    s.append(P("The outside of the coax shield is a conductor of its own. Whatever current the balun lets through flows on it: it radiates, "
               "distorts the pattern, picks up noise, and brings RF into the shack. Tick <b>Estimate coax common-mode current</b> and AntennaCalc "
               "models it the way NEC users do - the outside of the shield becomes a wire running from the balun straight down, then along at the "
               "coax run height in the direction you set to the radio (grounded there if ticked), joined to the antenna through the balun's "
               "common-mode impedance. The Geometry tab shows the route:"))
    s.append(bullets([
        "<b>Balun at the feedpoint</b> (no feed line): the coax is part of the antenna model, so the SWR, pattern and gain include it.",
        "<b>Balun at the bottom of a ladder line</b>: the ladder line is taken as balanced, so the coax is driven by half the voltage across the "
        "balun, against the ladder line and antenna. This is a separate estimate; it does not change the main result.",
        "The Matching tab shows the largest current on the coax, the current at the balun and at the radio, how far it is below the feed current "
        "(below -30 dB is good, -20 to -30 dB usually fine, above -20 dB the coax is part of the antenna), and the heat in the choke. "
        "A requirement check asks for at least 20 dB below the feed current."]))
    s.append(table([
        ["Antenna and balun (100 W, 15 m of RG-213 grounded at the radio)", "Most current on the coax", "Relative to feed", "Heat in the choke"],
        ["20 m dipole at 10 m, coax straight on (1:1 unun)", "111 mA", "-20 dB", "-"],
        ["the same, 1:1 voltage balun", "103 mA", "-21 dB", "-"],
        ["the same, 1:1 current balun, 2 kohm", "57 mA", "-26 dB", "0.2 W"],
        ["the same, 1:1 current balun, 5 kohm", "34 mA", "-30 dB", "0.2 W"],
        ["the same 2 kohm balun plus a 2 kohm choke 13 m down (at the shack)", "7 mA past the choke", "-44 dB", "0.6 W + 0.0 W"],
        ["40 m EFHW, 49:1 unun", "197 mA", "0 dB", "-"],
        ["40 m EFHW, 49:1 with a 2 kohm choke at the feedpoint", "239 mA", "+2 dB", "8.7 W"],
        ["40 m EFHW, 49:1 unun, 2 kohm choke 8 m down the coax", "88 mA past the choke", "-9 dB", "1.0 W"],
        ["40 m doublet, 20 m ladder line, 9:1 unun", "3.9 A", "+25 dB", "-"],
        ["the same, 9:1 current balun, 2 kohm", "215 mA", "0 dB", "37 W"]],
        [3.6 * inch, 1.2 * inch, 1.1 * inch, 1.3 * inch]))
    s.append(bullets([
        "On a dipole a good choke is what makes the difference; a voltage balun is little better than no balun.",
        "An EFHW <i>needs</i> current on its counterpoise. With an unun the coax is the counterpoise; a choke right at the feedpoint has to fight that "
        "and gets hot. The usual cure is a short counterpoise wire, or a choke some metres down the coax.",
        "An unun onto ladder line puts the coax straight into the antenna circuit - amps on the shield. A current balun stops most of it, but at the "
        "high-impedance bottom of a ladder line it must drop hundreds of volts of common-mode voltage, so it runs hot (37 W here). Use a choke of much "
        "higher impedance, a ladder line length that gives a lower impedance at the bottom, or take the ladder line all the way to a balanced tuner.",
        "The coax route matters: a coax that is near a quarter-wave long to its ground connection makes a resonant stub, with a small current at the "
        "balun and a large one at the radio. Try other coax lengths, or untick 'grounded at the radio', and compare.",
        "A choke only stops current that is <i>conducted</i> along the shield. Coax that runs close and parallel to a radiating wire - such as an "
        "EFHW counterpoise hanging next to it - picks up current along its length by induction, and a choke cannot stop that. Move the "
        "<b>Choke distance</b> along the coax and watch the current beyond it: on the EFHW above, chokes in the first 4 m (alongside the "
        "counterpoise) do not help, at 8 m one does. Route the coax away from the antenna as well as choking it."]))
    s.append(PageBreak())

    # ------------------------------------------------------------------ wire editor
    s.append(P("5. Drawing your own antenna: the Wire Editor", style_h1))
    s.append(P("When the antenna you want is not in the catalog - or you want to try your own idea - draw it. The <b>Wire Editor</b> "
               "lets you draw the wires, give them names, set their lengths with dimensions, and put sources (feed points) and loads "
               "(coils, capacitors, resistors, traps) anywhere on them. The drawing is then simulated by the same moment-method engine as "
               "the built-in wire antennas, so every result tab works: SWR, patterns, 3D, matching, multi-band, the PDF report and the NEC-2 export."))
    s.append(numbered([
        "Choose <b>Category: Custom</b> and <b>Antenna type: Custom wire antenna (Wire Editor)</b>, or use <b>Design &gt; Wire Editor</b> (Ctrl+E). "
        "The <b>Wire Editor</b> tab opens.",
        "Draw the antenna, start from a template (<b>New from template</b>), or start from a built-in design: run it, then use "
        "<b>Design &gt; Copy this design into the Wire Editor</b> (Ctrl+Shift+E). Its wires, feed points and loads (coils, traps, "
        "capacitors, loss resistors) become an editable drawing, with the tuned dimensions. Feed harnesses between elements (log-periodics, "
        "phased arrays) cannot be drawn, so their sources are set to the voltages the harness gives at the design frequency.",
        "Set the band, ground, conductor and feed system on the left panel as usual. The <b>height comes from the drawing</b>, so the height box is disabled.",
        "Press <b>ANALYSE</b> on the editor page (or DESIGN / F5). The Summary tab shows the result."]))
    s.append(shot("19g_copy_menu.png", "Starting from a built-in design: after running the loaded dipole, <b>Design &gt; Copy this design "
                  "into the Wire Editor</b> turns it into a drawing, coils included, that you can change and save as your own design.",
                  width=5.0 * inch))
    s.append(shot("19_editor.png", "The Wire Editor with a 40 m shortened dipole: two 6 m legs, a loading coil in each leg, the feed point "
                  "at the centre and a 'Span' dimension. Wire lengths are shown above each wire; the tables on the right hold the same data as numbers.",
                  width=6.6 * inch))

    s.append(P("Coordinates and views", style_h2))
    s.append(P("Everything is in metres. <b>X</b> and <b>Y</b> are horizontal and <b>Z</b> is the height above ground: the green hatched line "
               "is the ground (z = 0). A wire that ends on z = 0 is connected to the ground when a ground type is selected (a ground-mounted vertical, "
               "radials on the surface)."))
    s.append(table([
        ["Control", "What it does"],
        ["View", "<b>Front (X-Z)</b>, <b>Top (X-Y)</b> or <b>Side (Y-Z)</b>. You draw on a flat view; wires in front of or behind the drawing plane are still shown, projected."],
        ["Plane", "Where new points go along the viewing direction - e.g. in the front view, 'Plane Y = 3' draws the second element of a beam 3 m behind the first. "
                  "Points snapped to an existing wire end keep that end's full 3-D position."],
        ["Grid, Snap", "Grid spacing from 1 cm to 10 m. With Snap on, new points land on the grid and moved sources and loads step along their wire by a tenth of the grid."],
        ["Lengths, Labels", "Show or hide the length dimension of every wire and the wire / source / load names."],
        ["Fit", "Fit the whole drawing in the view (or press F). The mouse wheel zooms around the cursor; drag with the right or middle button "
                "(or the left button on empty space) to pan."]],
        [1.3 * inch, 5.9 * inch]))

    s.append(CondPageBreak(2.0 * inch))
    s.append(P("Drawing wires", style_h2))
    s += [
        numbered([
            "Click <b>Wire</b> (or press W).",
            "Click the start point, then click each next point: every click ends one wire and starts the next, so a whole inverted-V, loop or zig-zag is one run. "
            "A dashed line shows the wire being drawn with its length and angle.",
            "Hold <b>Shift</b> to draw at 15-degree steps (with Snap on, the length also steps by the grid).",
            "Right-click, double-click or press <b>Esc</b> to finish the run. Esc again returns to the Select tool."]),
        shot("19d_drawing.png", "Drawing an inverted-V: the second wire follows the cursor with its length and angle.", width=3.6 * inch)]
    s.append(bullets([
        "<b>Joining wires.</b> Wires are joined where their ends meet. A point snaps to a nearby wire end, which joins the two; ending a wire on the "
        "<i>middle</i> of another wire splits that wire there so the two are connected (a T-junction). Filled dots are joined ends, hollow dots are free ends.",
        "<b>Moving.</b> With <b>Select</b> (V), drag a wire end to move it - every wire joined at that point moves with it, so the antenna stays connected. "
        "Drag the middle of a wire to move the whole wire. Drop an end on another wire to join it.",
        "<b>Editing.</b> Double-click a wire for its properties: label, exact end coordinates and diameter (leave the diameter at 0 to use the "
        "conductor chosen on the left panel; set it for a thicker boom, mast or tube element). Right-click a wire for more: set length, split here, "
        "add a source or load here, add a length dimension, delete.",
        "<b>Templates</b> give a ready-made starting point sized for the design frequency: half-wave dipole, inverted-V, ground-mounted vertical, "
        "elevated ground plane with four sloping radials, and a full-wave quad loop.",
        "<b>Undo / Redo</b> (Ctrl+Z / Ctrl+Y) cover every change; <b>Delete</b> (or the Del key) removes the selected item; <b>Clear</b> empties the drawing."]))

    s.append(P("Labels and dimensions", style_h2))
    s.append(P("Each wire gets a label (W1, W2 ...) shown beside it; rename it in its properties or in the <b>Wires</b> table. Labels appear in the "
               "cut list on the Dimensions tab, so names such as 'Left leg' or 'Radial 1' make the results easy to read."))
    s.append(bullets([
        "<b>Wire lengths</b> are dimensioned automatically (true 3-D length, even for a wire that slopes away from you). "
        "<b>Double-click the length</b> to type a new one and choose which part stays put: the start, the end or the centre. "
        "Wires joined to the moving end follow it.",
        "<b>Dimension tool</b> (D): click one wire end, then another, to add a dimension between them - a span, a spacing between elements, "
        "a height difference. Double-click its value to give it a label and type a new distance: the second end (and everything joined to it) "
        "moves along the dimension line. Drag a dimension to move it clear of the wires.",
        "<b>Tables</b>: the Wires table on the right lists every end coordinate, length and diameter, and the Dimensions table every distance. "
        "Type a new number in a cell to change the drawing; select a row to highlight the item in the drawing."]))

    s.append(P("Sources and loads", style_h2))
    s.append(P("Choose <b>Source</b> (S) or <b>Load</b> (L) and click on a wire to place one there; its properties open at once. With Select, drag a source "
               "or load along its wire (it snaps to the ends and the middle), double-click it to edit it, or right-click a wire and choose "
               "<i>Add source here</i> / <i>Add load here</i>. Positions are measured from the start of the wire (the end you clicked first)."))
    s.append(bullets([
        "<b>Sources</b> are delta-gap voltage sources. The <b>first source is the feed point</b>: it is marked '(feed)' in the drawing and * in the table, "
        "and the SWR, impedance and matching results are for it. Add more sources with their own voltage and phase to drive a phased array; the port "
        "table on the Summary tab then lists every source.",
        "<b>Loads</b> are lumped impedances in series with the wire, in one of three forms:"]))
    s.append(table([
        ["Load type", "Impedance", "Use it for"],
        ["Fixed R + jX", "the same R and X at every frequency", "a terminating resistor (rhombic, T2FD, Beverage), a quick what-if"],
        ["Series R-L-C", "R + jwL + 1/(jwC); a value of 0 leaves that part out", "loading coils (L plus a few ohms of coil loss), series capacitors"],
        ["Parallel R-L-C (trap)", "R, L and C in parallel; 0 leaves a part out", "traps: L parallel C resonant at 1/(2 pi sqrt(LC)), with R for a lossy trap"]],
        [1.4 * inch, 2.6 * inch, 3.2 * inch]))
    pics = Table([[shot("19b_load_dialog.png", "Load properties: a 15.6 uH loading coil with 3 ohm loss.", width=2.5 * inch)._content,
                   shot("19c_editor_loads.png", "The Loads table. Double-click the type or value to open the properties.", width=4.2 * inch)._content]],
                 colWidths=[2.8 * inch, 4.4 * inch])
    pics.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    s.append(pics)
    s.append(callout("<b>Tip:</b> a source or load cannot sit on a <i>free</i> wire end - no current flows there. It can sit at a joint: where two wires meet "
                     "it goes between them (a centre-fed dipole drawn as two wires), and at a point where three or more wires meet, such as the base "
                     "of a ground plane, it is placed in a short feed gap just inside its own wire, which feeds that wire against all the others."))

    s.append(P("Analysing the drawing", style_h2))
    s.append(P("Press <b>ANALYSE</b>. Below the tables a line says <i>Ready</i> or lists what still needs doing (no wires, no source, a source on a free end, "
               "a wire below ground). The left panel supplies everything that is not in the drawing: the frequency and band, the ground, the conductor "
               "(for wires left at the default diameter), the transformer, coax and L-match, and the calculation quality."))
    s.append(bullets([
        "<b>Auto-tune</b> (Antenna options): 'Use the drawing as-is' analyses exactly what you drew. 'Scale whole antenna to resonance' grows or shrinks "
        "every dimension together until the feed point has no reactance at the design frequency (heights are scaled from the lowest point, so a "
        "ground-mounted antenna stays on the ground). The factor is shown in the Notes; <b>Apply tuned size</b> on the editor page copies the tuned "
        "size into the drawing.",
        "The <b>Dimensions</b> tab is the cut list: every wire with its length and ends, every source and load with its position.",
        "<b>File &gt; Save design</b> stores the drawing with the other inputs, and <b>Export NEC-2 deck</b> writes it out for 4nec2 or EZNEC."]))
    s.append(block(
        P("Example: a 40 m dipole only 12 m long", style_h3),
        P("A full-size 40 m dipole is about 20 m. Drawn as two 6 m legs at 10 m height (the picture at the start of this section), with a 15.6 uH coil "
          "(3 ohm loss) half way along each leg and the feed at the centre joint, it resonates near 7.2 MHz at about 45 ohm. To move resonance down to "
          "7.1 MHz, raise both coils slightly (about 16 uH) and analyse again. The result shows the price of the short wire: an SWR under 2:1 over only "
          "about 150 kHz, and an efficiency of about 65 % because of the coil loss and the low height."),
        shot("19f_editor_swr.png", "SWR / Impedance tab for the drawn 40 m shortened dipole.", width=5.0 * inch)))
    s.append(callout("<b>Good modelling practice:</b> keep wires that meet at an angle joined at their ends; avoid very short wires next to long ones "
                     "(the segments become unequal); keep wires at least a few diameters apart; and keep the ground connection to wires that really "
                     "touch the ground. Use 'Normal' or 'Fine' quality for the final numbers.", "warn"))
    s.append(P("Wire Editor keys", style_h3))
    s.append(table([["Key", "Action"], ["V / W / S / L / D", "Select / Wire / Source / Load / Dimension tool (click in the drawing first)"],
                    ["Shift (while drawing)", "15-degree steps"], ["Esc", "Finish the wire run; again for the Select tool"],
                    ["Del", "Delete the selected item"], ["F", "Fit the drawing in the view"], ["Ctrl+Z / Ctrl+Y", "Undo / redo"],
                    ["Double-click", "Edit a wire, source, load, or a length / dimension value"],
                    ["Right-click", "Context menu (or finish the current run)"]], [1.8 * inch, 5.4 * inch]))
    s.append(PageBreak())

    # ------------------------------------------------------------------ catalog
    s.append(P("6. Antenna catalog", style_h1))
    s.append(P("'Wire simulation' designs are solved with the moment-method engine for your exact dimensions, height and ground. 'Closed-form' designs use standard "
               "engineering formulas (the antenna is a dish, horn, patch, waveguide array or a small receive antenna that is not meaningfully modelled as thin wire)."))
    order = ["HF wire antennas", "Vertical antennas", "Directional beams", "Compact antennas", "VHF/UHF/satellite antennas",
             "Microwave antennas", "Receive-only antennas", "Custom"]
    rows = [["Antenna", "Method", "Notes"]]
    for cat in order:
        rows.append([f"<b>{cat}</b>", "", ""])
        for spec in [x for x in REGISTRY.values() if x.category == cat]:
            rows.append([spec.name, "Closed-form" if spec.analytic else "Wire simulation", spec.desc])
    t = table(rows, [2.5 * inch, 1.0 * inch, 3.7 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, r), (-1, r), colors.HexColor("#e8f0fe")) for r, row in enumerate(rows) if row[1] == "" and r > 0]))
    s.append(t)
    s.append(Spacer(1, 6))
    s.append(P("Dipole / Inverted-V / Sloper, Moxon / Hex beam, Yagi / spider beam, Magnetic loop (a hybrid: wire simulation for the pattern, resonator model for the SWR), "
               "and the rubber-duck whip (a coil-loaded whip) are the entries that cover several named types or use a simplified representation; the Notes tab says exactly how."))
    s.append(P("Several entries have a selector rather than a separate catalog line: the <b>Delta loop</b> covers apex up, apex down and horizontal (flat) triangles with a choice of "
               "feed point (middle of the base, a corner, or a slanted side), a tilt for vertical loops and a broadside direction; the <b>Half-square / Bobtail curtain</b> covers the "
               "2-vertical and 3-vertical arrays; and the <b>EFHW</b> offers a counterpoise style, transformer loss and compromise tuning across the harmonic bands. "
               "On the HF wire antennas and verticals the <i>Scan a frequency range</i> tick box (Calculation section) shows SWR from 1.8 to 55 MHz (or any Start/Stop you set)."))
    s.append(PageBreak())

    # ------------------------------------------------------------------ method
    s.append(P("7. How it calculates, and how far to trust it", style_h1))
    s.append(P("The wire engine", style_h2))
    s.append(bullets([
        "Each wire is divided into short segments (about a twentieth of a wavelength or less). The current on every segment is found by solving the electric-field integral equation "
        "with a mixed-potential formulation and piecewise-linear current basis functions - the same family of method as NEC.",
        "Junctions of any number of wires, lumped loads (traps, coils, resistors), voltage sources, transmission-line harnesses (LPDA) and ideal phasing currents (arrays) are supported.",
        "Skin-effect loss comes from the material conductivity and conductor diameter.",
        "Ground is modelled by the image method: exact for perfect ground, and with Fresnel reflection coefficients for real ground (the NEC 'reflection coefficient' approximation).",
        "Gain, patterns, efficiency and beamwidths are obtained from the far field; efficiency includes wire, load and ground loss."]))
    s.append(P("Known limits", style_h2))
    s.append(bullets([
        "Real-ground treatment is approximate for wires very close to the ground (beverage, flag, K9AY, wires under a metre high at HF).",
        "Conductors thicker than about 2% of a wavelength, or very small features such as the inside of a trap or a tuning capacitor, are not modelled in detail.",
        "Traps, coils and loads are lumped ideal components with the Q you give.",
        "The 'phased array' and 'cross-Yagi / turnstile / eggbeater' designs assume an ideal feed network; the port impedances tell you what the real network must match.",
        "The Sterba curtain and W8JK drive every section from an ideal in-phase (or anti-phase) source, so their feed impedance is the parallel combination - real open-wire phasing lines present several hundred ohms. The half-square, Bobtail and Bruce array are fed at one base against a radial system; the Bobtail and half-square feed point is several kilohms.",
        "Closed-form microwave models (dish, horn, patch, slot array) are estimates within a decibel or two; patch and slot patterns are simple approximations.",
        "Wire antennas near other conductors, buildings or trees, and the effect of masts, booms and insulators, are not included - trim on the air with an antenna analyser."]))
    s.append(callout("<b>Validation:</b> the half-wave dipole gives about 80 + j43 ohm and 2.12 dBi; a quarter-wave monopole over perfect ground gives half the dipole's impedance and 5.1 dBi; "
                     "a 3-element Yagi gives about 8 dBi free-space; these checks run automatically in tests/test_physics.py.", "tip"))
    s.append(P("8. Saving and exporting", style_h1))
    s.append(table([
        ["Action", "Where", "Result"],
        ["Save / Open design", "File menu (Ctrl+S / Ctrl+O)", "A .antcalc file with every input and the Wire Editor drawing; Open fills the panel and the drawing, then press DESIGN."],
        ["Export report (PDF)", "File menu (Ctrl+P)", "Summary, requirement checks, cut list, patterns, SWR, geometry, matching and notes in one PDF."],
        ["Export NEC-2 deck", "File menu", "A .nec file with the wires, ground, loads, sources and transmission lines for 4nec2, EZNEC or xnec2c to cross-check the result."],
        ["Export cut list / sweep (CSV)", "File menu or the tab buttons", "Spreadsheet-ready tables."],
        ["Theme", "View menu", "DAYLIGHT (light, the default) or SHACK (dark)."],
        ["Check for updates", "Help menu (tick)", "A few seconds after start the program asks GitHub whether a newer release exists. If so, an amber UPDATE vX.Y AVAILABLE button appears at the right of the status bar; click it to open the download page. Nothing is downloaded or installed for you and nothing is sent except the request itself. Untick to turn it off (for example when offline)."]],
        [1.8 * inch, 2.0 * inch, 3.4 * inch]))
    s.append(P("Keyboard shortcuts", style_h2))
    s.append(table([["Key", "Action"], ["F5", "Design"], ["F6", "Optimise (beams)"], ["Ctrl+E", "Open the Wire Editor"], ["Ctrl+S / Ctrl+O", "Save / open a design"],
                    ["Ctrl+P", "Export the PDF report"], ["F1", "Open this guide"], ["Ctrl+Q", "Quit"]], [1.8 * inch, 5.4 * inch]))
    s.append(P("Troubleshooting", style_h2))
    s.append(bullets([
        "<b>The SWR is high even though the antenna is 'tuned'.</b> Check the transformer ratio: a high- or low-impedance antenna (EFHW, loops, Yagis) needs the right ratio or the automatic L-match.",
        "<b>The result looks worse over the ground than in free space.</b> Ground loss and reflections matter: raise the antenna, or choose a better ground type, and compare with the free-space gain.",
        "<b>The gain target says FAIL.</b> The note on the Notes tab explains whether the size limit or the largest supported design stopped it; relax the limit or lower the target.",
        "<b>The calculation is slow.</b> Use 'Fast' quality while exploring, 'Normal' or 'Fine' for the final numbers.",
        "<b>A warning says the conductor is thick.</b> Thin-wire theory is less exact when the diameter exceeds about 2% of a wavelength (common on VHF/UHF with tube); expect small shifts in resonance."]))
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print("wrote", OUT_PATH)


if __name__ == "__main__":
    build()
