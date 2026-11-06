"""A release produced from a clone must be self-contained and exclude build caches."""
import hashlib
import importlib
import json
import zipfile
from pathlib import Path
import pytest

def test_release_from_arbitrary_clone_location(tmp_path,monkeypatch):
    from package_release import package_release
    base=tmp_path/'clone'; base.mkdir()
    for name in ['main.py','GearLab.spec','requirements.txt','README.md','README_RU.md','LICENSE','package_release.py','.gitignore','.gitattributes']:
        (base/name).write_text('test source',encoding='utf-8')
    (base/'dist/GearLab/_internal').mkdir(parents=True)
    (base/'dist/GearLab/GearLab.exe').write_bytes(b'fake exe for packaging test')
    (base/'dist/GearLab/_internal/runtime.dll').write_bytes(b'fake runtime')
    (base/'gearlab/__pycache__').mkdir(parents=True)
    (base/'gearlab/__init__.py').write_text('')
    (base/'gearlab/__pycache__/cache.pyc').write_bytes(b'cache')
    (base/'docs').mkdir(); (base/'docs/preview.png').write_bytes(b'preview')
    out=tmp_path/'custom-output'; package_release(base,out)
    assert (out/'GearLab/GearLab.exe').exists()
    assert len(list((out/'GearLab/Примеры').glob('*.gearlab')))==4
    with zipfile.ZipFile(out/'GearLab-Windows.zip') as archive:
        assert 'GearLab/_internal/runtime.dll' in archive.namelist()
        assert archive.testzip() is None
    with zipfile.ZipFile(out/'GearLab-source.zip') as archive:
        assert 'GearLab-source/docs/preview.png' in archive.namelist()
        assert all('__pycache__' not in x for x in archive.namelist())
    for line in (out/'SHA256SUMS.txt').read_text().splitlines():
        digest,name=line.split('  ')
        assert hashlib.sha256((out/name).read_bytes()).hexdigest()==digest

def test_missing_build_is_reported(tmp_path):
    from package_release import package_release
    with pytest.raises(FileNotFoundError,match='Build GearLab.spec first'):
        package_release(tmp_path,tmp_path/'release')
