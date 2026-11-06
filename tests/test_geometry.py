from dataclasses import replace
import math
import numpy as np
import pytest
from gearlab.parameters import Parameters,preset
from gearlab.geometry import make_mesh,mesh_report,export_stl,profile,transform
from gearlab.cad_export import export_step

CASES=[preset(12),preset(36),preset(48),preset(48,'left'),
       Parameters(kind='spur',teeth=24,module=1,bore=5,counterbore=0),
       Parameters(kind='herringbone',teeth=24,module=1,bore=5,counterbore=10),
       Parameters(kind='internal',teeth=48,module=1),
       Parameters(kind='rack',teeth=12,module=1),
       Parameters(kind='bevel',teeth=32,module=1,cone=15),
       Parameters(kind='worm',module=1,height=10,worm_diameter=16,starts=2),
       Parameters(kind='spur',teeth=30,module=1,bore=5,bore_shape='d',counterbore=0),
       Parameters(kind='spur',teeth=30,module=1,bore=5,bore_shape='hex',counterbore=0),
       Parameters(kind='helical',teeth=30,module=1,bore=0,counterbore=10,counter_depth=5)]

@pytest.mark.parametrize('p',CASES,ids=lambda p:f'{p.kind}-{p.teeth}-{p.bore_shape}-{p.hand}')
def test_export_roundtrip(p,tmp_path):
    from vtkmodules.vtkIOGeometry import vtkSTLReader
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    mesh,d=make_mesh(p); r=mesh_report(mesh)
    assert r['open_edges']==0 and r['components']==1 and r['volume']>0
    assert mesh.GetBounds()[4:]==pytest.approx((0,p.height))
    stl=tmp_path/'деталь.stl'; export_stl(mesh,stl)
    reader=vtkSTLReader(); reader.SetFileName(str(stl)); reader.Update()
    rr=mesh_report(reader.GetOutput()); assert rr['open_edges']==0 and rr['components']==1
    step=tmp_path/'деталь.step'; report=export_step(p,step)
    reader=STEPControl_Reader(); assert reader.ReadFile(str(step))==IFSelect_RetDone
    reader.TransferRoots(); shape=reader.OneShape(); assert BRepCheck_Analyzer(shape).IsValid()
    props=GProp_GProps(); BRepGProp.VolumeProperties_s(shape,props)
    assert report['solid_count']==1
    assert abs(props.Mass()-r['volume'])/props.Mass()<0.015

def test_measured_preset_and_helicity():
    p=preset(12); d=p.dimensions(); assert d['outside']==pytest.approx(7.8); assert d['root']==pytest.approx(5.5)
    mesh,_=make_mesh(p); assert mesh.GetBounds()==pytest.approx((-3.9,3.9,-3.9,3.9,0,10))
    q=replace(p,hand='right'); loop=profile(q)
    end=transform(loop,q,d,10); a0=math.atan2(loop[0,1],loop[0,0]); a1=math.atan2(end[0,1],end[0,0])
    assert a1-a0==pytest.approx(math.tan(math.radians(20))*10/d['rp'])
    q=replace(q,kind='herringbone'); assert transform(loop,q,q.dimensions(),10)[:,:2]==pytest.approx(loop)

def test_bore_and_shoulder_volume():
    p=Parameters(kind='spur',teeth=30,module=1,bore=0,counterbore=0)
    full,_=make_mesh(p); v0=mesh_report(full)['volume']
    p=replace(p,bore=2.8,counterbore=10,counter_depth=5)
    cut,_=make_mesh(p); v1=mesh_report(cut)['volume']
    expected=math.pi*1.4**2*5+math.pi*5**2*5
    assert v0-v1==pytest.approx(expected,rel=0.0002)

@pytest.mark.parametrize('changes',[{'bore':30},{'counter_depth':10},{'backlash':4},{'height':float('nan')},{'teeth':0},{'module':0}])
def test_invalid_dimensions(changes):
    with pytest.raises(ValueError): replace(preset(),**changes).dimensions()

def test_parameter_roundtrip():
    import json
    p=preset(12); assert Parameters.from_dict(json.loads(json.dumps(p.dict())))==p

def test_outside_mode():
    p=Parameters(sizing='outside',outside=40,root_override=0)
    assert p.dimensions()['outside']==pytest.approx(40)
