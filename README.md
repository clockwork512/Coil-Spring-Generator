# Coil Spring Designer

A desktop app for designing helical compression springs and exporting them as STEP or STL.

## Features

- **Spring rate (k)** estimated live as you type: `k = G·d⁴ / (8·D³·Na)`
- **Wire diameter**, with standard inch and metric wire-size lists
- **OD, ID or mean diameter**: pick which one you set; the others are calculated
- **End types**: open, open & ground, closed, closed & ground (total coils, solid height and free-length allowances follow Shigley)
- **Design target**: enter a target rate, or a force at a deflection or compressed length, and solve for active coils or wire diameter (optionally snapped to a standard size)
- **Checks**: stress at solid vs. allowable (Bergsträsser-corrected), spring index, buckling (L₀/D), pitch angle, natural frequency, OD growth at solid
- **Operating point**: force and stress at a given travel (e.g. 3 mm of compression) or at a working length
- **Previews**: rotatable 3D model, dimensioned side drawing, load–length chart
- **Export**: STEP solid (true B-rep, opens in SolidWorks, Fusion, Onshape, FreeCAD and others) or STL mesh. Ground ends are cut flat, and closed ends blend smoothly into the active coils.
- Units: inch/lbf, mm/N, or mm/kgf (stress in ksi, MPa or kgf/mm²); save and open designs as `.spring.json`; copy a text spec sheet to the clipboard

Exported CAD geometry is always in **millimetres**. Set your CAD import units to mm, or let it read the units from the STEP header.

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

## Engineering notes

- Material constants (G, Sut = A/dᵐ, allowable % of Sut at solid) come from Shigley Tables 10-4 to 10-6. Check them against your wire supplier's data for critical parts.
- The allowable stress check assumes the spring has been set-removed (pre-set). Without that, use roughly 70–80% of the shown allowable.
- In the CAD model, closed-end turns are given 0.5% of the wire diameter of clearance so that touching coils don't produce an invalid solid.
