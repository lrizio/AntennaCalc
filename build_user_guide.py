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
    return KeepTogether(list(flow))


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
        "<b>Practical outputs</b>: cut list in metres and feet/inches, weight, matching network values, multi-band performance table, NEC-2 export and a PDF report."]))
    s.append(P("Quick start", style_h2))
    s.append(numbered([
        "Pick a <b>Category</b> and an <b>Antenna type</b> at the top of the left panel.",
        "Choose the <b>Band</b> (or edit the design frequency and band edges).",
        "Optionally tick <b>Target gain</b> and/or <b>Size limit</b>.",
        "Choose the <b>Material</b> and <b>conductor diameter</b>, the <b>height</b> and the <b>ground</b>.",
        "Adjust the feed system (transformer, coax) and any <b>Antenna options</b> that appear for this type.",
        "Press <b>DESIGN</b> (F5). Results appear in the tabs on the right when the calculation finishes (a few seconds; large arrays take longer)."]))
    s.append(PageBreak())

    # ------------------------------------------------------------------ the window
    s.append(P("1. The window", style_h1))
    s.append(P("The left panel holds your requirements. The right side shows four-to-six headline cards (gain or directivity, front-to-back, SWR, "
               "bandwidth, take-off angle, efficiency) above nine tabs: <b>Summary, Dimensions, Patterns, SWR / Impedance, Geometry, 3D Pattern, Matching, Multi-band</b> and <b>Notes</b>."))
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
        ["Transformer, Coax, Length, System impedance", "Feed system between the antenna and the transmitter. Ratios such as 4:1, 9:1 and 49:1 are the common baluns and ununs. Coax loss is included in the SWR seen at the transmitter."],
        ["Automatic L-match", "Adds an ideal L-network at the feedpoint, calculated at the design frequency, so the antenna is matched to your system impedance. The values appear on the Matching tab."],
        ["Antenna options", "Settings special to the chosen design (number of radials, element count, traps, termination resistor, windings sense, and so on)."],
        ["Calculation", "Fast / Normal / Fine controls the number of wire segments per wavelength. Auto-tune trims lengths to resonance; Optimise (beams) refines spacings and lengths. "
         "<b>Sweep the whole HF range</b> (HF wire antennas and verticals) plots SWR and impedance from 1.8 to 30 MHz with the amateur bands shaded, "
         "so harmonic and multi-band behaviour is visible; it is on by default for the EFHW and takes a few seconds longer."]],
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
        "Red dots are feedpoints, amber squares are loads (traps, coils, resistors). The grid shows the ground when one is modelled.", "05_geometry.png", "Geometry tab.")
    sec("3D Pattern", "The radiation pattern as a shaded solid: the distance from the centre and the colour both show gain (the colour bar gives the scale, set by the same dB-scale box as the Patterns tab). "
        "Drag to rotate, wheel to zoom, and use the Oblique / Top / Side / Front buttons. The antenna itself is drawn inside the pattern (tick or untick <i>show antenna in the pattern</i>), so you can see which way each lobe points relative to the elements. The ring on the floor marks the horizon and N / E / S / W show the compass directions.",
        "05b_surface.png", "3D Pattern tab: a 3-element Yagi over ground.")
    sec("Matching", "Describes the whole feed system: antenna impedance, feeder line, L-network, transformer and coax, the impedance after matching, and a suggested "
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
               "AntennaCalc sweeps the whole HF range (the amateur bands are shaded) so you can see the evenly spaced dips, and offers these options:"))
    s.append(bullets([
        "<b>Tune the length for</b> - <i>All harmonic bands</i> (the default) lengthens the wire slightly so the 40/20/15/10 m dips fall on the bands, "
        "at the cost of the 80 m dip sitting a little low; <i>Fundamental band only</i> centres the lowest band and leaves the harmonics a few percent high.",
        "<b>Counterpoise</b> - length and direction of the return wire (the coax shield or a short wire). Hanging it down or away keeps the dips evenly spaced; "
        "in line with the radiator turns the antenna into an off-centre-fed dipole on the higher bands.",
        "<b>Transformer loss</b> - core loss of the 49:1 unun (default 0.5 dB when matched). It is what holds the SWR peaks between the dips to roughly 5-14:1 "
        "instead of 20 or more, and it costs a little transmit power at resonance.",
        "<b>Sweep the whole HF range</b> - the Calculation-section tick box, on by default for this antenna; untick for the usual band-only sweep (faster). "
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
    s.append(PageBreak())

    # ------------------------------------------------------------------ catalog
    s.append(P("5. Antenna catalog", style_h1))
    s.append(P("'Wire simulation' designs are solved with the moment-method engine for your exact dimensions, height and ground. 'Closed-form' designs use standard "
               "engineering formulas (the antenna is a dish, horn, patch, waveguide array or a small receive antenna that is not meaningfully modelled as thin wire)."))
    order = ["HF wire antennas", "Vertical antennas", "Directional beams", "Compact antennas", "VHF/UHF/satellite antennas",
             "Microwave antennas", "Receive-only antennas"]
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
               "On the HF wire antennas and verticals the <i>Sweep the whole HF range</i> tick box (Calculation section) shows SWR from 1.8 to 30 MHz."))
    s.append(PageBreak())

    # ------------------------------------------------------------------ method
    s.append(P("6. How it calculates, and how far to trust it", style_h1))
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
    s.append(P("7. Saving and exporting", style_h1))
    s.append(table([
        ["Action", "Where", "Result"],
        ["Save / Open design", "File menu (Ctrl+S / Ctrl+O)", "A .antcalc file with every input; Open fills the panel, then press DESIGN."],
        ["Export report (PDF)", "File menu (Ctrl+P)", "Summary, requirement checks, cut list, patterns, SWR, geometry, matching and notes in one PDF."],
        ["Export NEC-2 deck", "File menu", "A .nec file with the wires, ground, loads, sources and transmission lines for 4nec2, EZNEC or xnec2c to cross-check the result."],
        ["Export cut list / sweep (CSV)", "File menu or the tab buttons", "Spreadsheet-ready tables."],
        ["Theme", "View menu", "SHACK (dark) or DAYLIGHT (light)."],
        ["Check for updates", "Help menu (tick)", "A few seconds after start the program asks GitHub whether a newer release exists. If so, an amber UPDATE vX.Y AVAILABLE button appears at the right of the status bar; click it to open the download page. Nothing is downloaded or installed for you and nothing is sent except the request itself. Untick to turn it off (for example when offline)."]],
        [1.8 * inch, 2.0 * inch, 3.4 * inch]))
    s.append(P("Keyboard shortcuts", style_h2))
    s.append(table([["Key", "Action"], ["F5", "Design"], ["F6", "Optimise (beams)"], ["Ctrl+S / Ctrl+O", "Save / open a design"],
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
