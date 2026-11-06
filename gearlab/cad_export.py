"""Curved BRep export. OCCT is loaded only when STEP is requested."""
import math
import numpy as np
from .geometry import segments, bore_profile

def export_step(p,path):
    from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax3, gp_Pnt2d, gp_Dir2d, gp_Trsf, gp_Ax1
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
    from OCP.GeomAPI import GeomAPI_Interpolate
    from OCP.TColgp import TColgp_HArray1OfPnt
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.Geom import Geom_CylindricalSurface
    from OCP.Geom2d import Geom2d_Line
    from OCP.GCE2d import GCE2d_MakeSegment
    from OCP.BRepLib import BRepLib
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism, BRepPrimAPI_MakeCylinder
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell, BRepOffsetAPI_ThruSections
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    d=p.dimensions()
    def pt(xy,z=0): return gp_Pnt(float(xy[0]),float(xy[1]),z)
    def wire(seg):
        builder=BRepBuilderAPI_MakeWire()
        for kind,pts in seg:
            if np.linalg.norm(pts[0]-pts[-1])<1e-9: continue
            if kind=='line': edge=BRepBuilderAPI_MakeEdge(pt(pts[0]),pt(pts[-1])).Edge()
            elif kind=='arc':
                edge=BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(pt(pts[0]),pt(pts[len(pts)//2]),pt(pts[-1])).Value()).Edge()
            else:
                arr=TColgp_HArray1OfPnt(1,len(pts))
                for i,xy in enumerate(pts): arr.SetValue(i+1,pt(xy))
                curve=GeomAPI_Interpolate(arr,False,1e-7); curve.Perform()
                if not curve.IsDone(): raise ValueError('Не удалось построить эвольвенту')
                edge=BRepBuilderAPI_MakeEdge(curve.Curve()).Edge()
            builder.Add(edge)
        if not builder.IsDone(): raise ValueError('Контур STEP не замкнут')
        return builder.Wire()
    def moved(shape,z=0,angle=0,scale=1):
        t=gp_Trsf(); t.SetScale(gp_Pnt(0,0,0),scale)
        s=BRepBuilderAPI_Transform(shape,t,True).Shape()
        t=gp_Trsf(); t.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),angle)
        s=BRepBuilderAPI_Transform(s,t,True).Shape()
        t=gp_Trsf(); t.SetTranslation(gp_Vec(0,0,z))
        return BRepBuilderAPI_Transform(s,t,True).Shape()
    def sweep(w,h,angle):
        if abs(angle)<1e-9:
            return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(w).Face(),gp_Vec(0,0,h)).Shape()
        # Exact helix on an analytic cylindrical surface, as auxiliary trihedron.
        pitch=2*math.pi*h/abs(angle)
        surf=Geom_CylindricalSurface(gp_Ax3(gp_Pnt(0,0,0),gp_Dir(0,0,1)),1)
        line=Geom2d_Line(gp_Pnt2d(0,0),gp_Dir2d(2*math.pi*(1 if angle>0 else -1),pitch))
        end=line.Value(h/pitch*math.sqrt((2*math.pi)**2+pitch**2))
        seg=GCE2d_MakeSegment(line.Value(0),end).Value()
        aux=BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(seg,surf).Edge()).Wire()
        BRepLib.BuildCurves3d_s(aux,1e-7,MaxSegment=2000)
        spine=BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(gp_Pnt(0,0,0),gp_Pnt(0,0,h)).Edge()).Wire()
        pipe=BRepOffsetAPI_MakePipeShell(spine); pipe.SetMode(aux,False); pipe.Add(w); pipe.Build()
        if not pipe.IsDone() or not pipe.MakeSolid(): raise ValueError('Не удалось построить винтовую поверхность')
        return pipe.Shape()
    def cut(a,b):
        op=BRepAlgoAPI_Cut(a,b); op.Build()
        if not op.IsDone(): raise ValueError('Ошибка вычитания отверстия STEP')
        return op.Shape()
    w=wire(segments(p,d,25))
    angle=0
    if p.kind in ('helical','herringbone','internal'):
        angle=math.tan(d['beta'])*p.height/d['rp']*(1 if p.hand=='right' else -1)
    if p.kind=='worm': angle=2*p.height/(d['module']*p.starts)*(1 if p.hand=='right' else -1)
    if p.kind=='bevel':
        from OCP.TopoDS import TopoDS
        loft=BRepOffsetAPI_ThruSections(True,True,1e-7); loft.AddWire(w)
        loft.AddWire(TopoDS.Wire_s(moved(w,p.height,scale=d['scale']))); loft.Build()
        shape=loft.Shape()
    elif p.kind=='herringbone' and angle:
        from OCP.TopoDS import TopoDS
        lower=sweep(w,p.height/2,angle/2)
        upper=moved(sweep(TopoDS.Wire_s(moved(w,angle=angle/2)),p.height/2,-angle/2),p.height/2)
        op=BRepAlgoAPI_Fuse(lower,upper); op.Build(); shape=op.Shape()
    elif p.kind=='internal':
        shape=cut(BRepPrimAPI_MakeCylinder(d['rf']+p.rim,p.height).Shape(),sweep(w,p.height,angle))
    else: shape=sweep(w,p.height,angle)
    if p.kind not in ('rack','internal'):
        if p.bore:
            if p.bore_shape=='round': hole=BRepPrimAPI_MakeCylinder(p.bore/2,p.height).Shape()
            else:
                pts=bore_profile(p,256)
                if p.bore_shape=='d':
                    holewire=wire([('arc',pts),('line',np.array([pts[-1],pts[0]]))])
                else: holewire=wire([('line',np.array([a,b])) for a,b in zip(pts,np.roll(pts,-1,axis=0))])
                hole=BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(holewire).Face(),gp_Vec(0,0,p.height)).Shape()
            shape=cut(shape,hole)
        if d['counter']:
            shape=cut(shape,moved(BRepPrimAPI_MakeCylinder(p.counterbore/2,p.counter_depth).Shape(),p.height-p.counter_depth))
    if not BRepCheck_Analyzer(shape).IsValid(): raise ValueError('STEP не прошёл проверку геометрии OCCT')
    exp=TopExp_Explorer(shape,TopAbs_SOLID); count=0
    while exp.More(): count+=1; exp.Next()
    if count!=1: raise ValueError(f'Ожидалось одно твёрдое тело, получено {count}')
    props=GProp_GProps(); BRepGProp.VolumeProperties_s(shape,props)
    if props.Mass()<=0: raise ValueError('Нулевой объём STEP')
    Interface_Static.SetCVal_s('write.step.unit','MM')
    writer=STEPControl_Writer()
    if writer.Transfer(shape,STEPControl_AsIs)!=IFSelect_RetDone or writer.Write(str(path))!=IFSelect_RetDone:
        raise OSError('Не удалось записать STEP')
    return {'solid_count':count,'valid':True,'volume':props.Mass(),'units':'mm'}
