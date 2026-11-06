"""Create a self-contained portable release, notices, editable examples and source zip."""
import importlib.metadata as md
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from gearlab.parameters import preset

def package_release(base, out):
    """Package a built executable; paths depend only on the clone and --output."""
    base=Path(base).resolve(); out=Path(out).resolve()
    if not (base/'dist'/'GearLab'/'GearLab.exe').is_file():
        raise FileNotFoundError('Build GearLab.spec first: dist/GearLab/GearLab.exe is missing')
    release=out/'GearLab'
    release.mkdir(parents=True,exist_ok=True)
    shutil.copytree(base/'dist'/'GearLab',release,dirs_exist_ok=True)
    for name in ('README_RU.md','LICENSE'):
        shutil.copy2(base/name,release/name)
    lic=release/'licenses'; lic.mkdir(exist_ok=True)
    versions={}
    for name in ('PySide6-Essentials','shiboken6','numpy','vtk','cadquery-ocp','PyInstaller'):
        try: dist=md.distribution(name)
        except md.PackageNotFoundError: continue
        versions[name]=dist.version
        for file in dist.files or []:
            if any(x in str(file).lower() for x in ('license','copying','notice','copyright')):
                src=Path(dist.locate_file(file))
                if src.is_file():
                    target=lic/name/Path(str(file)); target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,target)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists(): shutil.copy2(python_license,lic/'Python-LICENSE.txt')
    versions['Python']=sys.version.split()[0]
    if (base/'third_party_licenses').exists(): shutil.copytree(base/'third_party_licenses',lic,dirs_exist_ok=True)
    (lic/'versions.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
    (lic/'README.txt').write_text('GearLab uses unmodified, dynamically loaded PySide6/Qt (LGPLv3), Shiboken, VTK (BSD), NumPy (BSD), OCP bindings (Apache-2.0), OCCT (LGPL with OCCT exception) and Python. Consult the accompanying component licenses. App sources and a reproducible build recipe are supplied in GearLab-source.zip. PyInstaller bootloader is covered by its distribution exception. Replacing a compatible shared library is possible by replacing files in _internal; no library integrity lock is applied. Qt source: https://code.qt.io/ and https://download.qt.io/official_releases/qtforpython/ ; OCCT source: https://github.com/Open-Cascade-SAS/OCCT ; OCP source: https://github.com/CadQuery/OCP ; VTK source: https://gitlab.kitware.com/vtk/vtk ; NumPy source: https://github.com/numpy/numpy',encoding='utf-8')
    examples=release/'Примеры'; examples.mkdir(exist_ok=True)
    for z,hand in [(12,'left'),(36,'right'),(48,'right'),(48,'left')]:
        (examples/f'gear_{z}_{hand}.gearlab').write_text(json.dumps({'format':'GearLab','version':1,'parameters':preset(z,hand).dict()},ensure_ascii=False,indent=2),encoding='utf-8')
    with zipfile.ZipFile(out/'GearLab-Windows.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(release.rglob('*')):
            if file.is_file(): archive.write(file,file.relative_to(out))
    with zipfile.ZipFile(out/'GearLab-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in ['main.py','GearLab.spec','requirements.txt','README.md','README_RU.md','LICENSE','package_release.py','.gitignore','.gitattributes']:
            archive.write(base/name,'GearLab-source/'+name)
        for folder in ('gearlab','tests','third_party_licenses','examples','docs','.github'):
            for file in sorted((base/folder).rglob('*')):
                if file.is_file() and '__pycache__' not in str(file): archive.write(file,'GearLab-source/'+file.relative_to(base).as_posix())
    sums=[]
    for name in ('GearLab-Windows.zip','GearLab-source.zip'):
        with (out/name).open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
        sums.append(f'{digest}  {name}')
    (out/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    return out

def main():
    base=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=base/'release',help='Destination directory (default: ./release)')
    args=parser.parse_args()
    try: out=package_release(base,args.output)
    except FileNotFoundError as e: parser.error(str(e))
    print('Release:',out/'GearLab')
    print('ZIP bytes:',(out/'GearLab-Windows.zip').stat().st_size)

if __name__=='__main__': main()
