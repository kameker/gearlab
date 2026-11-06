import json
import os
import sys
import time
from pathlib import Path
from dataclasses import replace
from PySide6 import QtCore, QtGui, QtWidgets as W
from PySide6.QtCore import Qt, Signal
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkActor, vtkPolyDataMapper, vtkLight
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
import vtkmodules.vtkRenderingOpenGL2  # register OpenGL rendering backend
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray, vtkPlane, vtkPlaneCollection
from vtkmodules.vtkFiltersGeneral import vtkClipClosedSurface
from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
from .parameters import Parameters, TYPES, preset
from .geometry import make_mesh, mesh_report, export_stl

STYLE='''
QWidget { color:#E9EEF5; font-family:"Segoe UI"; font-size:13px; }
QMainWindow, #root {background:#10151D;}
QFrame#header {background:#151C26;border-bottom:1px solid #293344;}
QLabel#brand {font-size:26px;font-weight:700;letter-spacing:1px;}
QLabel#subtitle {color:#92A1B5;font-size:12px;}
QLabel#logo {color:#70E0CF;font-size:30px;font-weight:700;}
QLabel#eyebrow {color:#76DFD1;font-size:11px;font-weight:700;letter-spacing:2px;}
QFrame#panel {background:#171F2A;border:1px solid #293547;border-radius:12px;}
QLabel#sectionTitle {font-size:15px;font-weight:600;}
QLabel#fieldLabel {color:#AFBDCF;}
QLabel#note {color:#91A3B9;font-size:12px;}
QLabel#status {color:#77DDC6;font-size:12px;}
QLabel#error {color:#FFAF91;font-size:12px;}
QPushButton {background:#232E3D;border:1px solid #354254;border-radius:7px;padding:8px 13px;}
QPushButton:hover {background:#303F52;border-color:#668491;}
QPushButton:pressed,QPushButton:checked {background:#245148;border-color:#68D7C4;}
QPushButton:disabled {color:#56677D;background:#1B2532;border-color:#293547;}
QPushButton#primary {background:#79E0CA;color:#102821;font-weight:700;border-color:#79E0CA;}
QPushButton#primary:hover {background:#9BEBD9;}
QPushButton#primary:disabled {background:#2B514B;color:#67877F;border-color:#2B514B;}
QDoubleSpinBox,QSpinBox,QComboBox {background:#101721;border:1px solid #344255;border-radius:6px;padding:7px 8px;min-height:19px;selection-background-color:#396B65;}
QDoubleSpinBox:focus,QSpinBox:focus,QComboBox:focus {border:1px solid #79E0CA;}
QComboBox QAbstractItemView {background:#1C2837;selection-background-color:#31554F;color:#EEF5FA;}
QTabWidget::pane {border:0;background:transparent;}
QTabBar::tab {color:#8FA2BA;background:#171F2A;padding:10px 11px;border-bottom:2px solid #293547;}
QTabBar::tab:selected {color:#78DFCD;border-bottom:2px solid #78DFCD;}
QScrollArea {border:0;background:transparent;}
QScrollArea>QWidget>QWidget {background:#171F2A;}
QScrollBar:vertical {background:#151D28;width:7px;margin:1px;}
QScrollBar::handle:vertical {background:#3B4B61;border-radius:3px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QCheckBox {color:#BDCAD9;spacing:7px;}
QCheckBox::indicator {width:15px;height:15px;background:#101721;border:1px solid #506277;border-radius:4px;}
QCheckBox::indicator:checked {background:#76DCC7;border-color:#76DCC7;}
QLabel#statValue {font-size:22px;font-weight:600;color:#F0F5FA;}
QLabel#statLabel {color:#8FA2B7;font-size:11px;}
QToolTip {background:#263648;color:#EFF5FB;border:1px solid #68818B;padding:7px;}
QProgressBar {border:0;background:#263447;height:3px;max-height:3px;}
QProgressBar::chunk {background:#78DFCD;}
'''

class JobSignals(QtCore.QObject):
    done=Signal(object,object)

class Job(QtCore.QRunnable):
    def __init__(self,fn):
        super().__init__(); self.fn=fn; self.signals=JobSignals()
    def run(self):
        try: self.signals.done.emit(self.fn(),None)
        except Exception as e: self.signals.done.emit(None,str(e))

def label(text,name=None):
    w=W.QLabel(text)
    if name: w.setObjectName(name)
    return w

class GearWindow(W.QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('GearLab — конструктор шестерён'); self.resize(1420,940); self.setMinimumSize(1050,760)
        self.pool=QtCore.QThreadPool(self); self.pool.setMaxThreadCount(2)
        self.params=preset(); self.mesh=None; self.current=None; self.revision=0; self.building=False; self.exporting=False; self.jobs=[]; self.widgets={}; self.rows={}
        self.timer=QtCore.QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(120); self.timer.timeout.connect(self.rebuild)
        self.setStyleSheet(STYLE)
        root=W.QWidget(); root.setObjectName('root'); self.setCentralWidget(root)
        layout=W.QVBoxLayout(root); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        head=W.QFrame(); head.setObjectName('header'); h=W.QHBoxLayout(head); h.setContentsMargins(24,15,24,15)
        h.addWidget(label('⚙','logo')); titles=W.QVBoxLayout(); titles.setSpacing(0); titles.addWidget(label('GearLab','brand')); titles.addWidget(label('Параметрический конструктор шестерён','subtitle')); h.addLayout(titles); h.addStretch()
        h.addWidget(label('WINDOWS  /  1.0','eyebrow')); h.addSpacing(20)
        for text,fn in [('Открыть',self.open_project),('Сохранить',self.save_project),('Справка',self.help)]:
            b=W.QPushButton(text); b.clicked.connect(fn); h.addWidget(b)
        layout.addWidget(head)
        body=W.QHBoxLayout(); body.setContentsMargins(18,18,18,12); body.setSpacing(16); layout.addLayout(body,1)
        panel=W.QFrame(); panel.setObjectName('panel'); panel.setFixedWidth(350); side=W.QVBoxLayout(panel); side.setContentsMargins(16,17,16,15); side.setSpacing(12)
        side.addWidget(label('01  /  ПАРАМЕТРЫ','eyebrow'))
        presets=W.QComboBox(); self.preset_combo=presets
        presets.addItem('Мои шестерни · выбрать пресет',None)
        for text,value in [('12T · Ø7,8 · левая',(12,'left')),('36T · Ø21,29 · правая',(36,'right')),('48T · Ø28,03 · правая',(48,'right')),('48T · Ø28,03 · левая',(48,'left'))]: presets.addItem(text,value)
        presets.activated.connect(self.load_preset); side.addWidget(presets)
        self.tabs=W.QTabWidget(); side.addWidget(self.tabs,1)
        form1=self.page('Зубья'); form2=self.page('Отверстие'); form3=self.page('Точность')
        self.combo(form1,'kind','Тип',[(v,k) for k,v in TYPES.items()])
        self.spin(form1,'teeth','Количество зубьев',6,300,integer=True)
        self.combo(form1,'sizing','Задать размер',[('По модулю','module'),('По наружному Ø','outside')])
        self.spin(form1,'module','Нормальный модуль, мм',.05,20,decimals=5,step=.05,tip='Для рейки и червяка — линейный / осевой модуль. Для косозубой шестерни — нормальный.')
        self.spin(form1,'outside','Наружный Ø, мм',.5,2000,decimals=3,step=.1)
        self.spin(form1,'height','Высота, мм',.2,300,step=.5)
        self.spin(form1,'pressure','Угол профиля, °',10,35,step=1)
        self.spin(form1,'helix','Наклон зубьев, °',0,50,step=1)
        self.combo(form1,'hand','Направление',[('Правое','right'),('Левое','left')])
        self.spin(form1,'backlash','Боковой зазор, мм',0,5,decimals=3,step=.02,tip='Уменьшение толщины наружного зуба по делительной окружности. Увеличение впадины внутреннего зуба. Это не припуск отверстия.')
        self.spin(form1,'root_override','Ø впадин вручную, мм',0,2000,decimals=3,step=.1,tip='0 = стандартная высота ножки 1,25 модуля. Ручной размер полезен для копирования измеренной детали.')
        self.spin(form1,'rim','Обод / основание, мм',.5,100,step=.5)
        self.spin(form1,'cone','Угол конуса, °',1,45,step=1)
        self.spin(form1,'starts','Заходов винта',1,8,integer=True)
        self.spin(form1,'worm_diameter','Наружный Ø винта, мм',1,500,step=.5)
        self.spin(form2,'bore','Сквозное отверстие, мм',0,500,decimals=3,step=.1,tip='0 = без отверстия. Для шестигранника — размер между гранями.')
        self.combo(form2,'bore_shape','Форма',[('Круглое','round'),('С лыской · D','d'),('Шестигранное','hex')])
        self.spin(form2,'flat','Глубина лыски, мм',.01,100,decimals=3,step=.1)
        form2.addRow(label('РАСТОЧКА С ВЕРХНЕЙ СТОРОНЫ','eyebrow'))
        self.spin(form2,'counterbore','Диаметр расточки, мм',0,500,decimals=3,step=.5)
        self.spin(form2,'counter_depth','Глубина расточки, мм',0,300,decimals=3,step=.5)
        note=label('Расточка начинается от верхнего торца Z = высота. Ноль в диаметре или глубине отключает её. Припуск на посадку задавайте в самом размере отверстия.','note'); note.setWordWrap(True); form2.addRow(note)
        self.hole_note=label('У рейки и внутренней шестерни эти отверстия не применяются.','note'); self.hole_note.setWordWrap(True); form2.addRow(self.hole_note)
        self.combo(form3,'quality','Сетка STL / просмотр',[('Быстро','draft'),('Высокая','fine'),('Максимальная','ultra')])
        info=label('STL хранит треугольную сетку. Все размеры — в миллиметрах. Высокая точность уменьшает грани на округлых поверхностях.\n\nSTEP сохраняет криволинейные поверхности и не зависит от выбранной точности сетки.\n\nЭвольвентные боковые поверхности. Подрезание, фаски и скругление у корня не строятся. Коническая модель и червяк — предварительные профили.','note'); info.setWordWrap(True); form3.addRow(info)
        self.warning=label('','note'); self.warning.setWordWrap(True); self.warning.setMinimumHeight(64); side.addWidget(self.warning)
        body.addWidget(panel)
        right=W.QVBoxLayout(); right.setSpacing(12); body.addLayout(right,1)
        toolbar=W.QHBoxLayout(); toolbar.addWidget(label('02  /  ЖИВОЙ ПРОСМОТР','eyebrow')); toolbar.addStretch()
        for text,fn in [('Изометрия',lambda:self.view('iso')),('Сверху',lambda:self.view('top')),('Спереди',lambda:self.view('front'))]:
            b=W.QPushButton(text); b.clicked.connect(fn); toolbar.addWidget(b)
        right.addLayout(toolbar)
        viewport=W.QFrame(); viewport.setObjectName('panel'); vv=W.QVBoxLayout(viewport); vv.setContentsMargins(1,1,1,1); vv.setSpacing(0)
        self.vtk=QVTKRenderWindowInteractor(viewport); vv.addWidget(self.vtk,1); right.addWidget(viewport,1)
        self.renderer=vtkRenderer(); self.renderer.SetBackground(.065,.09,.12); self.renderer.SetBackground2(.15,.19,.24); self.renderer.GradientBackgroundOn()
        self.vtk.GetRenderWindow().AddRenderer(self.renderer); self.vtk.GetRenderWindow().SetMultiSamples(4)
        interactor=self.vtk.GetRenderWindow().GetInteractor(); interactor.SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        self.mapper=vtkPolyDataMapper(); self.mapper.ScalarVisibilityOff(); self.shading=vtkPolyDataNormals(); self.shading.SplittingOn(); self.shading.SetFeatureAngle(25); self.shading.ConsistencyOn(); self.actor=vtkActor(); self.actor.SetMapper(self.mapper)
        prop=self.actor.GetProperty(); prop.SetColor(.88,.66,.32); prop.SetAmbient(.18); prop.SetDiffuse(.72); prop.SetSpecular(.65); prop.SetSpecularPower(45)
        self.renderer.AddActor(self.actor); self.grid=vtkActor(); self.grid.GetProperty().SetColor(.29,.38,.47); self.grid.GetProperty().SetOpacity(.3); self.renderer.AddActor(self.grid)
        light=vtkLight(); light.SetLightTypeToSceneLight(); light.SetPosition(-70,-80,100); light.SetIntensity(.65); self.renderer.AddLight(light)
        headlight=vtkLight(); headlight.SetLightTypeToHeadlight(); headlight.SetIntensity(.8); self.renderer.AddLight(headlight)
        tools=W.QHBoxLayout(); tools.setContentsMargins(12,8,12,8); tools.setSpacing(16)
        for text,attr in [('Каркас','wire'),('Разрез','section'),('Сетка','grid_check')]:
            cb=W.QCheckBox(text); setattr(self,attr,cb); cb.setChecked(attr=='grid_check'); cb.toggled.connect(self.display_options); tools.addWidget(cb)
        tools.addStretch(); tools.addWidget(label('ЛКМ · вращение   |   Колесо · масштаб','note')); vv.addLayout(tools)
        self.stat_labels={}; stats=W.QHBoxLayout(); stats.setSpacing(10)
        for key,title in [('outside','НАРУЖНЫЙ Ø · ММ'),('pitch','ДЕЛИТЕЛЬНЫЙ Ø · ММ'),('height','ВЫСОТА · ММ'),('module','МОДУЛЬ · ММ')]:
            card=W.QFrame(); card.setObjectName('panel'); c=W.QVBoxLayout(card); c.setContentsMargins(14,10,14,11); c.setSpacing(1)
            value=label('—','statValue'); self.stat_labels[key]=value; c.addWidget(value); c.addWidget(label(title,'statLabel')); stats.addWidget(card)
        right.addLayout(stats)
        foot=W.QHBoxLayout(); self.status=label('Построение модели…','status'); foot.addWidget(self.status,1)
        self.stl_button=W.QPushButton('Экспорт STL'); self.stl_button.setObjectName('primary'); self.stl_button.clicked.connect(lambda:self.export('stl')); foot.addWidget(self.stl_button)
        self.step_button=W.QPushButton('Экспорт STEP'); self.step_button.clicked.connect(lambda:self.export('step')); foot.addWidget(self.step_button); right.addLayout(foot)
        self.progress=W.QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); layout.addWidget(self.progress)
        bottom=W.QHBoxLayout(); bottom.setContentsMargins(20,4,20,10); bottom.addWidget(label('Все размеры в мм  •  локальная работа  •  без подключения к интернету','note')); bottom.addStretch(); bottom.addWidget(label('Предварительную модель проверьте пробной печатью','note')); layout.addLayout(bottom)
        self.vtk.Initialize(); self.load_parameters(self.params)
        icon=QtGui.QPixmap(64,64); icon.fill(Qt.GlobalColor.transparent); painter=QtGui.QPainter(icon); painter.setPen(QtGui.QColor('#78DFCD')); painter.setFont(QtGui.QFont('Segoe UI Symbol',44)); painter.drawText(icon.rect(),Qt.AlignmentFlag.AlignCenter,'⚙'); painter.end(); self.setWindowIcon(QtGui.QIcon(icon))

    def page(self,title):
        scroll=W.QScrollArea(); scroll.setWidgetResizable(True); host=W.QWidget(); form=W.QFormLayout(host); form.setContentsMargins(0,16,8,10); form.setVerticalSpacing(11); form.setHorizontalSpacing(8); form.setRowWrapPolicy(W.QFormLayout.RowWrapPolicy.WrapAllRows); scroll.setWidget(host); self.tabs.addTab(scroll,title); return form
    def spin(self,form,key,title,low,high,decimals=2,step=1,integer=False,tip=None):
        widget=W.QSpinBox() if integer else W.QDoubleSpinBox()
        widget.setRange(low,high); widget.setSingleStep(step); widget.setKeyboardTracking(False)
        if not integer: widget.setDecimals(decimals)
        if tip: widget.setToolTip(tip)
        widget.valueChanged.connect(self.changed); self.add_field(form,key,title,widget)
    def combo(self,form,key,title,options):
        widget=W.QComboBox()
        for text,value in options: widget.addItem(text,value)
        widget.currentIndexChanged.connect(self.changed); self.add_field(form,key,title,widget)
    def add_field(self,form,key,title,widget):
        l=label(title,'fieldLabel'); form.addRow(l,widget); self.widgets[key]=widget; self.rows[key]=(form,l,widget)
    def read_parameters(self):
        values={}
        for k,w in self.widgets.items(): values[k]=w.currentData() if isinstance(w,W.QComboBox) else w.value()
        # Keep full precision of untouched fields (especially the normal module in presets).
        for k,v in values.items():
            if isinstance(self.widgets[k],W.QDoubleSpinBox) and v==round(getattr(self.params,k),self.widgets[k].decimals()): values[k]=getattr(self.params,k)
        return Parameters(**values)
    def load_parameters(self,p):
        self.params=p
        for k,w in self.widgets.items():
            w.blockSignals(True)
            if isinstance(w,W.QComboBox): w.setCurrentIndex(w.findData(getattr(p,k)))
            else: w.setValue(getattr(p,k))
            w.blockSignals(False)
        self.changed()
    def load_preset(self,index):
        data=self.preset_combo.itemData(index)
        if data: self.load_parameters(preset(*data))
    def visibility(self,p):
        specific={'helix':p.kind in ('helical','herringbone','internal'),'hand':p.kind in ('helical','herringbone','internal','worm'),
                  'root_override':p.kind not in ('internal','rack','worm'),'rim':p.kind in ('internal','rack'),
                  'cone':p.kind=='bevel','starts':p.kind=='worm','worm_diameter':p.kind=='worm',
                  'teeth':p.kind!='worm','sizing':p.kind not in ('internal','rack','worm'),
                  'module':p.sizing=='module' or p.kind in ('internal','rack','worm'),
                  'outside':p.sizing=='outside' and p.kind not in ('internal','rack','worm'),
                  'flat':p.bore_shape=='d','backlash':p.kind!='worm','pressure':p.kind!='worm'}
        for key,visible in specific.items():
            form,l,w=self.rows[key]; l.setVisible(visible); w.setVisible(visible)
        for key in ('bore','bore_shape','flat','counterbore','counter_depth'):
            self.widgets[key].setEnabled(p.kind not in ('internal','rack'))
        self.hole_note.setVisible(p.kind in ('internal','rack'))
    def changed(self,*args):
        self.params=self.read_parameters(); self.visibility(self.params); self.revision+=1; self.stl_button.setEnabled(False); self.step_button.setEnabled(False)
        try:
            self.params.dimensions(); self.status.setText('Обновление модели…'); self.status.setObjectName('status'); self.timer.start()
        except Exception as e:
            self.timer.stop(); self.show_error(str(e))
    def show_error(self,text):
        self.status.setText('Исправьте параметры'); self.warning.setText(text); self.warning.setObjectName('error'); self.warning.style().unpolish(self.warning); self.warning.style().polish(self.warning)
        self.stl_button.setEnabled(False); self.step_button.setEnabled(False); self.actor.SetVisibility(False); self.vtk.GetRenderWindow().Render()
    def start_job(self,fn,callback):
        job=Job(fn); self.jobs.append(job)
        def finish(result,error):
            callback(result,error)
            if job in self.jobs: self.jobs.remove(job)
        job.signals.done.connect(finish); self.pool.start(job)
    def rebuild(self):
        if self.building: self.timer.start(); return
        p=replace(self.params); revision=self.revision; self.building=True; start=time.perf_counter()
        def done(result,error):
            self.building=False
            if revision!=self.revision: return
            if error: self.show_error(error); return
            mesh,d=result; report=mesh_report(mesh)
            if report['open_edges'] or report['components']!=1:
                self.show_error('Не удалось замкнуть модель. Измените параметры.'); return
            first=self.mesh is None; self.mesh=mesh; self.current=replace(p); self.actor.SetVisibility(True); self.mapper.SetInputData(mesh); self.update_grid(mesh)
            self.display_options()
            if first: self.view('iso')
            for key,w in self.stat_labels.items(): w.setText(f"{(p.height if key=='height' else d[key]):.3f}".rstrip('0').rstrip('.'))
            if p.kind=='rack': self.stat_labels['outside'].setText('—'); self.stat_labels['pitch'].setText('—')
            self.warning.setObjectName('note'); self.warning.setText('\n'.join(d['warnings']) or 'Модель проверена: замкнутая сетка, одно тело.'); self.warning.style().unpolish(self.warning); self.warning.style().polish(self.warning)
            self.status.setText(f"{report['triangles']:,}".replace(',',' ')+' треуг. · '+f'{time.perf_counter()-start:.2f} с · готово')
            self.stl_button.setEnabled(not self.exporting); self.step_button.setEnabled(not self.exporting)
        self.start_job(lambda:make_mesh(p),done)
    def update_grid(self,mesh):
        bounds=mesh.GetBounds(); span=max(bounds[1]-bounds[0],bounds[3]-bounds[2]); size=max(5,span*.8); step=10**int(__import__('math').floor(__import__('math').log10(max(span/10,.1))))
        if size/step>30: step*=5
        pts=vtkPoints(); cells=vtkCellArray(); i=0
        import numpy as np
        for a in np.arange(-size,size+step*.5,step):
            for pair in [((-size,a,-.15),(size,a,-.15)),((a,-size,-.15),(a,size,-.15))]:
                for v in pair: pts.InsertNextPoint(*v)
                cells.InsertNextCell(2); cells.InsertCellPoint(i); cells.InsertCellPoint(i+1); i+=2
        pd=vtkPolyData(); pd.SetPoints(pts); pd.SetLines(cells); mapper=vtkPolyDataMapper(); mapper.SetInputData(pd); self.grid.SetMapper(mapper)
    def display_options(self,*args):
        if self.mesh is None: return
        if self.section.isChecked():
            plane=vtkPlane(); plane.SetOrigin(0,0,0); plane.SetNormal(0,1,0); planes=vtkPlaneCollection(); planes.AddItem(plane)
            clip=vtkClipClosedSurface(); clip.SetInputData(self.mesh); clip.SetClippingPlanes(planes); clip.SetTolerance(1e-7); clip.Update(); self.clip=clip; self.shading.SetInputData(clip.GetOutput())
        else: self.shading.SetInputData(self.mesh)
        self.shading.Update(); self.mapper.SetInputConnection(self.shading.GetOutputPort())
        if self.wire.isChecked(): self.actor.GetProperty().SetRepresentationToWireframe()
        else: self.actor.GetProperty().SetRepresentationToSurface()
        self.grid.SetVisibility(self.grid_check.isChecked()); self.renderer.ResetCameraClippingRange(); self.vtk.GetRenderWindow().Render()
    def view(self,name):
        if self.mesh is None: return
        b=self.mesh.GetBounds(); center=((b[0]+b[1])/2,(b[2]+b[3])/2,(b[4]+b[5])/2); camera=self.renderer.GetActiveCamera()
        vectors={'iso':(1,-1.4,1.1),'top':(0,0,1),'front':(0,-1,0)}; v=vectors[name]
        camera.SetFocalPoint(*center); camera.SetPosition(*(center[i]+v[i]*100 for i in range(3))); camera.SetViewUp(0,1,0) if name=='top' else camera.SetViewUp(0,0,1); camera.ParallelProjectionOn(); self.renderer.ResetCamera(self.mesh.GetBounds()); camera.Zoom(1.02); self.renderer.ResetCameraClippingRange(); self.vtk.GetRenderWindow().Render()
    def save_project(self):
        path,_=W.QFileDialog.getSaveFileName(self,'Сохранить параметры','шестерня.gearlab','Проект GearLab (*.gearlab)')
        if not path: return
        try:
            self.params.dimensions(); Path(path).write_text(json.dumps({'format':'GearLab','version':1,'parameters':self.params.dict()},ensure_ascii=False,indent=2),encoding='utf-8'); self.status.setText('Параметры сохранены')
        except Exception as e: W.QMessageBox.warning(self,'Сохранение',str(e))
    def open_project(self):
        path,_=W.QFileDialog.getOpenFileName(self,'Открыть параметры','','Проект GearLab (*.gearlab)')
        if not path: return
        try:
            if Path(path).stat().st_size>100_000: raise ValueError('Слишком большой файл проекта')
            data=json.loads(Path(path).read_text(encoding='utf-8'))
            if data.get('format')!='GearLab' or data.get('version')!=1: raise ValueError('Неизвестный формат проекта')
            self.load_parameters(Parameters.from_dict(data['parameters']))
        except Exception as e: W.QMessageBox.warning(self,'Открытие',str(e))
    def export(self,kind):
        if self.current is None or self.exporting: return
        p=replace(self.current); mesh=self.mesh
        default=f'gear_{p.kind}_{p.teeth}T.{kind}'
        path,_=W.QFileDialog.getSaveFileName(self,'Экспорт '+kind.upper(),default,f'{kind.upper()} (*.{kind})')
        if path: self.export_to(path,kind,p,mesh)
    def export_to(self,path,kind,p=None,mesh=None,finished=None):
        if self.exporting: return
        p=p or replace(self.current); mesh=mesh or self.mesh; self.exporting=True; self.progress.show(); self.stl_button.setEnabled(False); self.step_button.setEnabled(False); self.status.setText('Сохранение '+kind.upper()+'…')
        def write():
            dest=Path(path); tmp=dest.with_name(dest.stem+'.gearlab-tmp'+dest.suffix)
            try:
                if kind=='step':
                    from .cad_export import export_step
                    report=export_step(p,tmp)
                else: report=export_stl(mesh,tmp)
                os.replace(tmp,dest); return report
            finally:
                if tmp.exists(): tmp.unlink()
        def done(report,error):
            self.exporting=False; self.progress.hide(); valid=self.current==self.params; self.stl_button.setEnabled(valid); self.step_button.setEnabled(valid)
            if error:
                self.status.setText('Ошибка экспорта')
                if not finished: W.QMessageBox.warning(self,'Экспорт',error)
            else: self.status.setText('Сохранено: '+Path(path).name)
            if finished: finished(report,error)
        self.start_job(write,done)
    def help(self):
        box=W.QMessageBox(self); box.setWindowTitle('GearLab · краткая справка'); box.setTextFormat(Qt.TextFormat.RichText)
        box.setText('<h2>GearLab 1.0</h2><p>Измените параметры — 3D-модель обновится автоматически. ЛКМ вращает, колесо меняет масштаб, Shift + ЛКМ сдвигает камеру.</p><p><b>Косозубые пары:</b> для параллельных валов нужны одинаковые нормальный модуль, угол профиля и величина наклона, но противоположное направление зубьев. Цепочка 12 → 48 → 48: левая → правая → левая.</p><p><b>Ступенчатое отверстие:</b> задайте сквозное Ø2,8 мм, расточку Ø10 мм и глубину 5 мм. «Разрез» меняет только просмотр.</p><p><b>Экспорт:</b> STL в миллиметрах для печати; STEP для КОМПАС и других CAD. Сохранение проекта хранит редактируемые параметры.</p><p>Конический профиль и червяк предварительные. Подрезание, скругления у корня и контакт пары не рассчитываются. Углы пресетов 20° приняты по исходному описанию, а не измерены. Перед нагрузкой проверьте зацепление и пробную печать.</p>')
        box.exec()
    def closeEvent(self,event):
        if self.exporting:
            self.status.setText('Дождитесь завершения экспорта'); event.ignore(); return
        self.timer.stop(); self.pool.waitForDone(); self.vtk.Finalize(); event.accept()
