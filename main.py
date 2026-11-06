import os
import sys
from pathlib import Path

def main():
    from PySide6 import QtCore, QtWidgets
    QtCore.QLocale.setDefault(QtCore.QLocale('ru_RU'))
    QtCore.QCoreApplication.setOrganizationName('GearLab')
    QtCore.QCoreApplication.setApplicationName('GearLab')
    app=QtWidgets.QApplication(sys.argv)
    from gearlab.gui import GearWindow
    window=GearWindow(); window.show()
    if '--smoke-test' in sys.argv:
        import json, time
        from gearlab.parameters import preset
        from gearlab.geometry import mesh_report
        out=Path(sys.argv[sys.argv.index('--smoke-test')+1]); out.mkdir(parents=True,exist_ok=True)
        state={'stage':0,'start':time.monotonic()}; timer=QtCore.QTimer(); timer.setInterval(150)
        def tick():
            if time.monotonic()-state['start']>120:
                (out/'failure.txt').write_text('Smoke test timed out',encoding='utf-8'); timer.stop(); app.exit(2); return
            if window.mesh is None or window.building or window.timer.isActive() or window.exporting or window.current!=window.params: return
            if state['stage']==0:
                window.repaint(); app.processEvents()
                window.screen().grabWindow(int(window.winId())).save(str(out/'GearLab-preview.png')); window.load_parameters(preset(12)); state['stage']=1
            elif state['stage']==1:
                state['report12']=mesh_report(window.mesh); window.load_parameters(preset(48)); state['stage']=2
            elif state['stage']==2:
                window.section.setChecked(True); window.repaint(); app.processEvents(); window.screen().grabWindow(int(window.winId())).save(str(out/'GearLab-section.png')); window.section.setChecked(False)
                state['stage']=3
                def result(report,error):
                    if error: state['error']=error
                    else: state['stl']=report
                window.export_to(out/'smoke48.stl','stl',finished=result)
            elif state['stage']==3:
                state['stage']=4
                def result(report,error):
                    if error: state['error']=error
                    else: state['step']=report
                window.export_to(out/'smoke48.step','step',finished=result)
            elif state['stage']==4:
                timer.stop(); (out/'smoke-report.json').write_text(json.dumps(state,indent=2),encoding='utf-8'); window.close(); app.exit(1 if 'error' in state else 0)
        timer.timeout.connect(tick); timer.start()
    return app.exec()

if __name__=='__main__':
    try: sys.exit(main())
    except Exception:
        import traceback
        log=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'GearLab'/'error.log'
        log.parent.mkdir(parents=True,exist_ok=True); log.write_text(traceback.format_exc(),encoding='utf-8')
        try:
            from PySide6.QtWidgets import QApplication,QMessageBox
            app=QApplication.instance() or QApplication(sys.argv); QMessageBox.critical(None,'GearLab',f'Ошибка запуска. Журнал: {log}\n'+traceback.format_exc()[-1400:])
        except Exception: pass
        sys.exit(1)
