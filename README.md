# AntennaCalc

**Design amateur-radio antennas to your requirements** - band, gain target, size limit, conductor material and size, height and ground - and get the dimensions, expected performance and matching.

Site: https://lrizio.github.io/AntennaCalc/ &nbsp;|&nbsp; Download: see [Releases](https://github.com/lrizio/AntennaCalc/releases) (Windows, no install)

![AntennaCalc](docs/guide/02_yagi_summary.png)

* **46 antenna designs** in seven categories: HF wire, verticals, directional beams, compact/loaded, VHF/UHF/satellite, microwave, receive-only (dipoles, OCFD, G5RV, fan/trap dipoles, EFHW, loops, rhombic, GP, J-pole, Yagi, quad, LPDA, Moxon, phased arrays, helix, dish, horn, patch, slot arrays, magnetic loop, K9AY and many more).
* **Real simulation** for wire antennas with a built-in thin-wire method-of-moments solver (`antennacalc/mom.py`): impedance, SWR sweep, gain, patterns, efficiency, ground effects, traps, coils, loads, phased feeds, LPDA harness.
* **Gain target + size limit**: beams pick their own element count. **Auto-tune** and an **optimiser** for gain / front-to-back.
* Results: PASS/FAIL checks, cut list (m and ft/in) with weight, azimuth/elevation patterns, rotatable 3-D pattern with the antenna drawn inside it, SWR and impedance, matching network values, multi-band table, PDF report, NEC-2 export.

## Run from source

```
pip install PySide6 numpy scipy
python main.py
```
Tests: `pip install pytest` then `python -m pytest tests -q`. Build the exe: `python build_exe.py`.

## Accuracy and safety

Results are engineering estimates; always trim on an antenna analyser. See [DISCLAIMER.md](DISCLAIMER.md). Licence: [MIT](LICENSE).

73 de VK3EI
