from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs
site=Path(sys.prefix)/'Lib'/'site-packages'
binaries=collect_dynamic_libs('OCP')
for folder in ('cadquery_ocp.libs','vtk.libs'):
    binaries += [(str(p),folder) for p in (site/folder).glob('*.dll')]
hidden=collect_submodules('OCP')+['vtkmodules.qt.PySide6','vtkmodules.util.numpy_support']
a=Analysis(['main.py'],pathex=[str(Path(SPECPATH))],binaries=binaries,datas=[],
           hiddenimports=hidden,excludes=['matplotlib','scipy','IPython','tkinter','PyQt5','PyQt6','PySide2','cadquery','casadi','numba','pandas'],noarchive=False)
# Qt uses Windows' ICU API. An unrelated Poppler ICU on the build host PATH
# has versioned symbols and must never shadow the operating system library.
a.binaries=[entry for entry in a.binaries if Path(entry[0]).name.lower() not in {'icuuc.dll','icuin.dll','icudt.dll'}]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='GearLab',debug=False,bootloader_ignore_signals=False,
        strip=False,upx=False,console=False,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='GearLab')
