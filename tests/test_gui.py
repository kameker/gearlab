import json
import time
from pathlib import Path
import pytest
from PySide6 import QtWidgets as W,QtCore
from gearlab.gui import GearWindow
from gearlab.parameters import preset

def idle(app,window):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        app.processEvents(); time.sleep(.01)
        if not window.timer.isActive() and not window.building and not window.exporting and window.current==window.params:
            return
    raise AssertionError('Model update did not complete')

def test_interaction_save_restore_and_recover(tmp_path,monkeypatch):
    app=W.QApplication.instance() or W.QApplication([])
    window=GearWindow(); window.show(); idle(app,window)
    try:
        old=window.mesh.GetNumberOfCells()
        # Real widget signal -> debounce -> worker -> render mapper.
        window.widgets['teeth'].setValue(60); idle(app,window)
        assert window.current.teeth==60 and window.mesh.GetNumberOfCells()!=old
        window.widgets['bore'].setValue(200); app.processEvents()
        assert not window.stl_button.isEnabled() and not window.actor.GetVisibility()
        window.load_parameters(preset(12)); idle(app,window)
        assert window.actor.GetVisibility() and window.stl_button.isEnabled()
        path=tmp_path/'проект.gearlab'
        monkeypatch.setattr(W.QFileDialog,'getSaveFileName',lambda *a,**kw:(str(path),''))
        window.save_project(); assert json.loads(path.read_text(encoding='utf-8'))['parameters']['teeth']==12
        window.load_parameters(preset(48)); idle(app,window)
        monkeypatch.setattr(W.QFileDialog,'getOpenFileName',lambda *a,**kw:(str(path),''))
        window.open_project(); idle(app,window); assert window.current.teeth==12
        window.section.setChecked(True); assert window.mapper.GetInput().GetNumberOfCells()>0
        window.wire.setChecked(True); window.view('top'); window.view('front'); window.view('iso')
        window.section.setChecked(False); window.wire.setChecked(False)
        result=[]; path=tmp_path/'экспорт.stl'
        window.export_to(path,'stl',finished=lambda report,error:result.append((report,error))); idle(app,window)
        assert result and result[0][1] is None and path.stat().st_size>1000
    finally:
        window.close(); app.processEvents()
