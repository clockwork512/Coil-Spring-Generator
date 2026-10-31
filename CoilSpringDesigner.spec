# PyInstaller spec – build with:  pyinstaller CoilSpringDesigner.spec
# Produces dist/CoilSpringDesigner/ (folder build; faster startup than one-file).
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("OCP", "cadquery", "OpenGL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
# pyqtgraph: skip its examples/jupyter modules (importing them during analysis crashes)
datas += collect_data_files("pyqtgraph")
hiddenimports += collect_submodules(
    "pyqtgraph", filter=lambda n: not any(x in n for x in ("examples", "jupyter", "canvas", "flowchart")))

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["vtkmodules", "vtkmodules.all"],
    excludes=["tkinter", "matplotlib", "IPython", "jupyter_client", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="CoilSpringDesigner",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="CoilSpringDesigner")
