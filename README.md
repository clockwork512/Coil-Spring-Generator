# Coil Spring Designer

A desktop app **and a website you can host on your own computer** for designing helical compression springs and exporting them as STEP or STL. Both use the same calculation, material and CAD code.

## Features

- **Spring rate (k)** estimated live as you type: `k = G·d⁴ / (8·D³·Na)`
- **Wire diameter**, with a separate wire-size chart for each material (optionally with tensile strength per size)
- **OD, ID or mean diameter**: pick which one you set; the others are calculated
- **End types**: open, open & ground, closed, closed & ground (total coils, solid height and free-length allowances follow Shigley)
- **Design target**: enter a target rate, or a force at a deflection or compressed length, and solve for active coils or wire diameter (optionally snapped to a standard size)
- **Checks**: stress at solid vs. allowable (Bergsträsser-corrected), spring index, buckling (L₀/D), pitch angle, natural frequency, OD growth at solid
- **Operating point**: force and stress at a given travel (e.g. 3 mm of compression) or at a working length
- **Clamping pressure page**: N identical springs in parallel at a displacement on a contact area. Gives total force, pressure (psi / MPa / kPa / kgf/cm²) and a low–high band from the deflection stack-up and spring-rate tolerance, using either the spreadsheet method or a true worst case. The spring can come from the current design (with a wire-stress check) or from catalog values.
- **Previews**: rotatable 3D model, dimensioned side drawing, load–length chart
- **Export**: STEP solid (true B-rep, opens in SolidWorks, Fusion, Onshape, FreeCAD and others) or STL mesh. Ground ends are cut flat, and closed ends blend smoothly into the active coils.
- **Developer mode** (desktop app and website): click **Developer** in the toolbar (in the desktop app you can also press **F12**; in a browser F12 opens the browser's own tools). A small **ƒ** appears next to every calculated value; click it to open the calculation inspector at the bottom of the window. It shows the variable's formula, the formula with the actual numbers substituted, the result (in the internal units mm, N, MPa and as displayed), what it depends on and what uses it (click to jump), and the exact line of source code that computes it. Each value is cross-checked against the number the app is showing (✓). The **Calculation log** tab lists every step in order and can be copied.
- **Light and dark themes**: use the Theme menu in the toolbar (Dark, Light or Follow system). Colours are defined in `coilspring/theme.py`.
- Units: inch/lbf, mm/N, or mm/kgf (stress in ksi, MPa or kgf/mm²); save and open designs as `.spring.json`; copy a text spec sheet to the clipboard

Exported CAD geometry is always in **millimetres**. Set your CAD import units to mm, or let it read the units from the STEP header.

## Website (host it from your laptop)

1. Double-click **`run_web_windows.bat`**. The first time, it sets up Python and the packages, which takes a few minutes. After that it starts in a few seconds.
2. A window opens showing the addresses, and your browser opens the site:
   ```
   On this computer:   http://localhost:8000
   For coworkers:      http://YOUR-LAPTOP-NAME:8000
                       http://10.x.x.x:8000
   ```
3. Send coworkers the **For coworkers** address. If the name doesn't work for them, use the numbered address.
4. Leave the window open while people use the site. Close it, or press Ctrl+C, to stop.

**The first time on Windows**, a Windows Firewall prompt asks about Python. Tick **Private networks** and click **Allow**. If you missed it, open Windows Security → Firewall & network protection → Allow an app through firewall, and tick Private for `python.exe`.

**Notes**
- The site is only available while your laptop is on, awake and on the company network. To stop Windows sleeping, use Settings → System → Power & battery → Screen and sleep.
- Your Wi-Fi or Ethernet connection should be set to the **Private** network profile. Some company networks block computers from reaching each other; if coworkers can't connect, that's a question for IT.
- There is no login. Anyone on your network who has the address can use the site, so don't open it on public or guest Wi-Fi.
- To keep the site to your own computer: `run_web_windows.bat --local`. To use another port: `run_web_windows.bat --port 8080`.
- Each person's inputs, units and theme are remembered in their own browser. **Save…** and **Open…** use the same `.spring.json` files as the desktop app, so designs move between the two.
- Exports run on your laptop, one at a time. A STEP file takes about a second.

## Python requirement

You need **64-bit Python 3.10–3.13**. The CAD library (`cadquery-ocp`) isn't published for newer Python versions, 32-bit Python or ARM64 Python on Windows. If pip reports *"conflicting dependencies… no matching distributions available for cadquery-ocp"*, that's the cause. Install Python 3.12 using the "Windows installer (64-bit)" from python.org; it can be installed alongside your existing Python. On ARM/Snapdragon PCs, use the x64 installer too.

`build_windows.bat` finds a compatible Python automatically through the `py` launcher.

## Run from source

```
python -m venv .venv
.venv\Scripts\activate          (Windows)   |   source .venv/bin/activate   (macOS/Linux)
pip install -r requirements.txt
python run.py
```

## Build a standalone app

- **Windows:** double-click `build_windows.bat`, then run `dist\CoilSpringDesigner\CoilSpringDesigner.exe`. After the build has set things up, `run_windows.bat` starts the app straight from source.
- **macOS/Linux:** `./build_mac_linux.sh`, then run `dist/CoilSpringDesigner/CoilSpringDesigner`

The build folder is large (1–2 GB) because it bundles the OpenCASCADE CAD kernel. You can zip the whole `dist/CoilSpringDesigner` folder and copy it to any machine running the same OS; Python is not needed there.

## Files

| File | Purpose |
|---|---|
| `coilspring/calc.py` | Spring math and material table. No GUI dependency, so it can be reused in scripts. |
| `coilspring/geometry.py` | Variable-pitch centreline, preview mesh, STEP/STL solid |
| `coilspring/views.py` | 3D view, drawing, load chart |
| `coilspring/app.py` | Main window |
| `coilspring/clamp.py` | Springs-in-parallel force and pressure math |
| `coilspring/clamp_page.py` | Clamping pressure page |
| `coilspring/theme.py` | Dark and light colour themes |
| `coilspring/trace.py` | Developer mode: step-by-step trace of every formula, with source lines and cross-checks |
| `coilspring/dev_panel.py` | Developer mode: ƒ buttons and the calculation inspector panel |
| `run_web.py`, `run_web_windows.bat` | Start the website |
| `coilspring/web/server.py` | Website API (reuses calc, clamp and geometry) |
| `coilspring/web/static/` | Website pages: `index.html`, `app.js`, `style.css`, and three.js for the 3D view (in `vendor/`, so it works without internet) |
| `assets/icon.ico`, `assets/icon.png` | App icon (`.exe` and window); redraw with `python assets/make_icon.py` |

## Materials and wire charts

Materials live in `coilspring/calc.py`, in the `MATERIALS` block: currently music wire (ASTM A228) and 17-7 PH (CH900). Each one has a `chart` list of the wire sizes you can get. That list fills the **Std…** dropdown, and **Solve wire Ø** snaps to it. An entry can be a diameter alone (`0.080`) or a diameter with its minimum tensile strength (`(0.080, 284)`, in ksi for an inch chart or MPa for a mm chart). Once two or more sizes have a tensile value, the app interpolates strength from the chart instead of using the A/dᵐ formula.

## Engineering notes

- Material constants (G, Sut = A/dᵐ, allowable % of Sut at solid) come from Shigley Tables 10-4 to 10-6. Check them against your wire supplier's data for critical parts.
- The allowable stress check assumes the spring has been set-removed (pre-set). Without that, use roughly 70–80% of the shown allowable.
- In the CAD model, closed-end turns are given 0.5% of the wire diameter of clearance so that touching coils don't produce an invalid solid.
