"""Parametric profiles and watertight, millimetre meshes; no CAD kernel in live view."""
import math
import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy, numpy_to_vtkIdTypeArray
from vtkmodules.vtkCommonCore import vtkPoints, vtkIdList
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray
from vtkmodules.vtkFiltersGeneral import vtkContourTriangulator
from vtkmodules.vtkFiltersCore import vtkCleanPolyData, vtkPolyDataNormals, vtkFeatureEdges, vtkTriangleFilter, vtkMassProperties, vtkPolyDataConnectivityFilter
from vtkmodules.vtkIOGeometry import vtkSTLWriter

def polar(r,a):
    a=np.asarray(a)
    return np.column_stack((r*np.cos(a),r*np.sin(a)))

def circle(radius, n=192, clockwise=False):
    return polar(radius, np.linspace(0,(-1 if clockwise else 1)*2*np.pi,n,endpoint=False))

def segments(p, d=None, samples=12):
    """Closed CCW contour as (line/arc/spline, XY samples), preserving CAD curves."""
    d=d or p.dimensions(); n=p.teeth; m=d['module']; pi=np.pi
    if p.kind=='rack':
        pitch=pi*m; a=math.tan(math.radians(p.pressure)); length=n*pitch
        pts=[[-length/2,-1.25*m-p.rim],[length/2,-1.25*m-p.rim],[length/2,-1.25*m]]
        for k in reversed(range(n)):
            x=(k+0.5)*pitch-length/2
            b=pi*m/4+1.25*m*a-p.backlash/2; t=pi*m/4-m*a-p.backlash/2
            pts += [[x+b,-1.25*m],[x+t,m],[x-t,m],[x-b,-1.25*m]]
        pts += [[-length/2,-1.25*m]]
        pts=np.asarray(pts,float)
        return [('line',np.array([pts[i],pts[(i+1)%len(pts)]])) for i in range(len(pts)) if np.linalg.norm(pts[i]-pts[(i+1)%len(pts)])>1e-9]
    if p.kind=='worm':
        # Trapezoidal thread in a section normal to the screw axis.
        count=p.starts; rr=d['rf']; ra=d['ra']; result=[]
        for k in range(count):
            c=2*pi*k/count; pitch=2*pi/count
            angles=np.array([-.5,-.32,-.16,.16,.32,.5])*pitch+c
            radii=[rr,rr,ra,ra,rr,rr]
            pts=np.column_stack((np.cos(angles)*radii,np.sin(angles)*radii))
            for j in range(5):
                if j in (0,2,4):
                    result.append(('arc',polar(radii[j],np.linspace(angles[j],angles[j+1],max(3,samples)))))
                else: result.append(('line',pts[j:j+2]))
        return result
    rp,rb,ra,rf=d['rp'],d['rb'],d['ra'],d['rf']
    result=[]
    if p.kind=='internal':
        ts=math.sqrt((ra/rb)**2-1); te=math.sqrt((rf/rb)**2-1)
        hb=pi/(2*n)-(math.tan(d['alpha'])-d['alpha'])-p.backlash/(2*rp)
        half=lambda t: hb+t-np.arctan(t)
        for k in range(n):
            c=k*2*pi/n; t=np.linspace(te,ts,samples)
            result.append(('spline',polar(rb*np.sqrt(1+t*t),c-half(t))))
            result.append(('arc',polar(ra,np.linspace(c-half(ts),c+half(ts),max(3,samples//2)))))
            t=np.linspace(ts,te,samples)
            result.append(('spline',polar(rb*np.sqrt(1+t*t),c+half(t))))
            result.append(('arc',polar(rf,np.linspace(c+half(te),c+2*pi/n-half(te),max(3,samples//2)))))
        return result
    ts=math.sqrt(max(0,(rf/rb)**2-1)); te=math.sqrt(max(0,(ra/rb)**2-1)); hb=d['halfbase']
    half=lambda t: hb-t+np.arctan(t)
    for k in range(n):
        c=k*2*pi/n; start=polar(rf,[c-half(ts)])[0]; end=polar(rb*np.sqrt(1+ts*ts),[c-half(ts)])[0]
        if rf<rb: result.append(('line',np.array([start,end])))
        t=np.linspace(ts,te,samples)
        result.append(('spline',polar(rb*np.sqrt(1+t*t),c-half(t))))
        result.append(('arc',polar(ra,np.linspace(c-half(te),c+half(te),max(3,samples//2)))))
        t=np.linspace(te,ts,samples)
        result.append(('spline',polar(rb*np.sqrt(1+t*t),c+half(t))))
        if rf<rb: result.append(('line',np.array([polar(rb,[c+hb])[0],polar(rf,[c+hb])[0]])))
        result.append(('arc',polar(rf,np.linspace(c+half(ts),c+2*pi/n-half(ts),max(3,samples//2)))))
    return result

def profile(p,d=None,samples=12):
    return np.concatenate([pts[:-1] for kind,pts in segments(p,d,samples)])

def bore_profile(p,n=192):
    if not p.bore: return None
    if p.bore_shape=='hex':
        return circle(p.bore/math.sqrt(3),6)
    if p.bore_shape=='d':
        r=p.bore/2; a=math.acos((r-p.flat)/r)
        return polar(r,np.linspace(a,2*np.pi-a,n))
    return circle(p.bore/2,n)

def transform(loop,p,d,z):
    theta=0
    if p.kind in ('helical','herringbone','internal'):
        ze=min(z,p.height-z) if p.kind=='herringbone' else z
        theta=math.tan(d['beta'])/d['rp']*ze*(1 if p.hand=='right' else -1)
    if p.kind=='worm':
        theta=2*math.pi*z/(math.pi*d['module']*p.starts)*(1 if p.hand=='right' else -1)
    co,si=math.cos(theta),math.sin(theta)
    xy=loop @ np.array([[co,si],[-si,co]])
    if p.kind=='bevel': xy=xy*(1-z*math.tan(math.radians(p.cone))/d['rp'])
    return np.column_stack((xy,np.full(len(xy),z)))

def polydata(vertices,faces):
    pd=vtkPolyData(); points=vtkPoints(); points.SetData(numpy_to_vtk(np.asarray(vertices,dtype=np.float64),deep=True)); pd.SetPoints(points)
    cells=vtkCellArray(); f=np.asarray(faces,dtype=np.int64); data=np.column_stack((np.full(len(f),3),f)).ravel()
    cells.SetCells(len(f),numpy_to_vtkIdTypeArray(data,deep=True)); pd.SetPolys(cells)
    return pd

def make_mesh(p):
    d=p.dimensions(); samples={'draft':6,'fine':14,'ultra':26}[p.quality]
    circular={'draft':96,'fine':256,'ultra':512}[p.quality]
    contour=profile(p,d,samples)
    points=[]; faces=[]
    def add(vertices):
        ix=len(points); points.extend(np.asarray(vertices).tolist()); return np.arange(ix,len(points))
    def sides(loops):
        indexes=[add(loop) for loop in loops]
        for lo,hi in zip(indexes,indexes[1:]):
            for i in range(len(lo)):
                j=(i+1)%len(lo); faces.extend(((lo[i],lo[j],hi[j]),(lo[i],hi[j],hi[i])))
    def cap(loops,z,up):
        pp=[]; lines=vtkCellArray()
        for loop in loops:
            if loop is None: continue
            start=len(pp); pp.extend(np.column_stack((loop,np.full(len(loop),z))).tolist())
            for j in range(len(loop)):
                lines.InsertNextCell(2); lines.InsertCellPoint(start+j); lines.InsertCellPoint(start+(j+1)%len(loop))
        pd=vtkPolyData(); pts=vtkPoints(); pts.SetData(numpy_to_vtk(np.asarray(pp,dtype=np.float64),deep=True)); pd.SetPoints(pts); pd.SetLines(lines)
        tri=vtkContourTriangulator(); tri.SetInputData(pd); tri.Update()
        if tri.GetTriangulationError():
            if len([v for v in loops if v is not None])!=1:
                raise ValueError('Не удалось построить торец: контуры пересекаются')
            # Long collinear rack roots need the simple-polygon triangulator.
            polygon=vtkCellArray(); polygon.InsertNextCell(len(pp))
            for j in range(len(pp)): polygon.InsertCellPoint(j)
            simple=vtkPolyData(); simple.SetPoints(pts); simple.SetPolys(polygon)
            fallback=vtkTriangleFilter(); fallback.SetInputData(simple); fallback.Update(); output=fallback.GetOutput()
        else: output=tri.GetOutput()
        vertices=vtk_to_numpy(output.GetPoints().GetData()); base=add(vertices)
        ids=vtkIdList(); cells=output.GetPolys(); cells.InitTraversal()
        while cells.GetNextCell(ids):
            ix=[ids.GetId(j) for j in range(3)]; a,b,c=vertices[ix]
            if (np.cross(b-a,c-a)[2]>0)!=up: ix[1],ix[2]=ix[2],ix[1]
            faces.append(tuple(base[ix]))
    total_twist=0
    if p.kind in ('helical','herringbone','internal'): total_twist=math.tan(d['beta'])*p.height/d['rp']
    if p.kind=='worm': total_twist=2*p.height/(d['module']*p.starts)
    step={'draft':8,'fine':3,'ultra':1.5}[p.quality]
    count=max(1,int(math.ceil(abs(math.degrees(total_twist))/step)))
    # A visible guard keeps extreme screws from exhausting memory.
    if count*len(contour)>1_500_000: raise ValueError('Слишком сложная сетка: уменьшите высоту, зубья или точность')
    levels=list(np.linspace(0,p.height,count+1))
    if p.kind=='herringbone': levels.append(p.height/2)
    if d['counter'] and p.kind not in ('internal','rack'): levels.append(p.height-p.counter_depth)
    levels=sorted(set(levels))
    if p.kind=='internal':
        outer=circle(d['rf']+p.rim,circular)
        sides([np.column_stack((outer,np.full(len(outer),z))) for z in (0,p.height)])
        sides([transform(contour[::-1],p,d,z) for z in levels])
        cap([outer,contour[::-1]],0,False)
        cap([outer,transform(contour,p,d,p.height)[:,:2][::-1]],p.height,True)
    else:
        sides([transform(contour,p,d,z) for z in levels])
        hole=None if p.kind=='rack' else bore_profile(p,circular)
        counter=d['counter'] and p.kind!='rack'
        shoulder=p.height-p.counter_depth if counter else p.height
        if hole is not None:
            sides([np.column_stack((hole[::-1],np.full(len(hole),z))) for z in (0,shoulder)])
        top_hole=circle(p.counterbore/2,circular) if counter else hole
        if counter:
            sides([np.column_stack((top_hole[::-1],np.full(len(top_hole),z))) for z in (shoulder,p.height)])
            cap([top_hole,hole[::-1] if hole is not None else None],shoulder,True)
        cap([contour,hole[::-1] if hole is not None else None],0,False)
        cap([transform(contour,p,d,p.height)[:,:2],top_hole[::-1] if top_hole is not None else None],p.height,True)
    pd=polydata(points,faces)
    clean=vtkCleanPolyData(); clean.SetInputData(pd); clean.ToleranceIsAbsoluteOn(); clean.SetAbsoluteTolerance(1e-8); clean.Update()
    normals=vtkPolyDataNormals(); normals.SetInputConnection(clean.GetOutputPort()); normals.SplittingOff(); normals.ConsistencyOn(); normals.AutoOrientNormalsOn(); normals.ComputePointNormalsOn(); normals.Update()
    out=vtkPolyData(); out.DeepCopy(normals.GetOutput())
    return out,d

def mesh_report(mesh):
    edge=vtkFeatureEdges(); edge.SetInputData(mesh); edge.BoundaryEdgesOn(); edge.NonManifoldEdgesOn(); edge.FeatureEdgesOff(); edge.ManifoldEdgesOff(); edge.Update()
    mass=vtkMassProperties(); mass.SetInputData(mesh); mass.Update()
    cc=vtkPolyDataConnectivityFilter(); cc.SetInputData(mesh); cc.SetExtractionModeToAllRegions(); cc.Update()
    return dict(vertices=mesh.GetNumberOfPoints(), triangles=mesh.GetNumberOfCells(),
                open_edges=edge.GetOutput().GetNumberOfCells(),components=cc.GetNumberOfExtractedRegions(),
                volume=mass.GetVolume(), bounds=list(mesh.GetBounds()))

def export_stl(mesh,path):
    report=mesh_report(mesh)
    if report['open_edges'] or report['components']!=1 or report['volume']<=0:
        raise ValueError('Сетка не прошла проверку замкнутости')
    writer=vtkSTLWriter(); writer.SetFileName(str(path)); writer.SetInputData(mesh); writer.SetFileTypeToBinary()
    if not writer.Write(): raise OSError('Не удалось записать STL')
    return report
