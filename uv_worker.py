"""Isolated, bounded UV generation. No padding reduction or automatic upscaling."""
import json
import math
import sys
import time
from pathlib import Path
import hou
from hlod_progress_io import publish, read_progress


def atomic(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def repair_uv(flat_geo, bad_ids):
    geo=hou.Geometry()
    geo.merge(flat_geo)
    for slot,index in enumerate(sorted(bad_ids)):
        t=geo.prim(index)
        vs=t.vertices()
        if len(vs)!=3: raise ValueError('Expected a triangle for UV repair')
        pos=[tuple(v.point().position()) for v in vs]
        def sub(a,b): return tuple(x-y for x,y in zip(a,b))
        def dot(a,b): return sum(x*y for x,y in zip(a,b))
        es=[sub(pos[(i+1)%3],pos[i]) for i in range(3)]
        i=max(range(3),key=lambda j:dot(es[j],es[j]))
        a,b,c=vs[i],vs[(i+1)%3],vs[(i+2)%3]
        edge=es[i]; delta=sub(pos[(i+2)%3],pos[i]); length2=dot(edge,edge)
        cross=tuple(edge[(k+1)%3]*delta[(k+2)%3]-edge[(k+2)%3]*delta[(k+1)%3] for k in range(3))
        if not length2 or not dot(cross,cross):raise ValueError('Zero 3D area on '+str(index))
        origin=-2.-3.*slot
        a.setAttribValue('uv',(origin,0.,0.)); b.setAttribValue('uv',(origin+1.,0.,0.))
        c.setAttribValue('uv',(origin+dot(delta,edge)/length2,(dot(cross,cross)**.5)/length2,0.))
    return geo


def run(config_path):
    cfg = json.loads(Path(config_path).read_text(encoding='utf-8'))
    report_path = Path(cfg['report'])
    report = {'algorithm': 'autoseam-flatten-v2', 'resolution': cfg['resolution'],
              'minimumResolution': cfg['minimumResolution'], 'paddingPixelsAtMinimum': 8, 'timings': {}}
    def stage(label):
        path = Path(cfg['progress'])
        state = read_progress(path)
        if state is not None:
            state.update(phase=label, stepStarted=time.time())
            publish(path, state)
        print(label, flush=True)
    def cook(node, label):
        stage(label)
        started = time.monotonic()
        node.cook(force=True)
        if node.errors():
            raise RuntimeError(str(node.errors()))
        report['timings'][label] = time.monotonic() - started
    container = hou.node('/obj').createNode('geo', 'HLOD_UV')
    source = container.createNode('file', 'reduced_input', exact_type_name=True)
    source.parm('file').set(cfg['input'])
    seams = container.createNode('uvautoseam', 'auto_seams', exact_type_name=True)
    seams.setInput(0, source)
    seams.setParms({'graintol': .3, 'mergethreshold': .7})
    flat = container.createNode('uvflatten::3.0', 'flatten', exact_type_name=True)
    flat.setInput(0, seams)
    flat.setParms({'seamgroup': 'seams', 'layoutseamgroup': 'seams', 'manuallayout': 1})
    cook(flat, 'UV AutoSeam + Flatten')
    flat.geometry().saveToFile(cfg['flattened'])
    layout = container.createNode('uvlayout::3.0', 'layout', exact_type_name=True)
    layout.setInput(0, flat)
    # Preserve eight pixels of spacing at the explicitly selected smallest output size.
    padding = 8.0 * cfg['resolution'] / cfg['minimumResolution']
    layout.setParms({'padding': padding, 'resolution': 'custom', 'customresolution': cfg['resolution'],
                     'correctareas': 1, 'packincavities': 0, 'iterations': 1})
    layout.setDisplayFlag(True)
    hou.hipFile.save(cfg['hip'])
    cook(layout, 'UV Layout（保持最小尺寸间距）')
    def uv_area(prim):
        uv = [v.attribValue('uv')[:2] for v in prim.vertices()]
        # Translate to the first vertex to avoid cancellation at large UV offsets.
        return abs(sum((uv[i][0]-uv[0][0])*(uv[i+1][1]-uv[0][1])-
                       (uv[i+1][0]-uv[0][0])*(uv[i][1]-uv[0][1]) for i in range(1,len(uv)-1)))*.5
    report['alignmentFallback'] = False
    if any(uv_area(p)==0 for p in layout.geometry().prims()):
        # Intrinsic island alignment can collapse very thin UV triangles at float precision.
        # Retry the same islands/size/padding without that rotation before asking for more pages.
        layout.parm('axisalignislands').set(0)
        report['alignmentFallback'] = True
        cook(layout, 'UV Layout 重试（关闭岛轴对齐，保持间距）')
        hou.hipFile.save(cfg['hip'])
    report['flattenMethod'] = 'scp'
    if report['alignmentFallback'] and any(uv_area(p)==0 for p in layout.geometry().prims()):
        flat.parm('method').set('abf')
        report['flattenMethod'] = 'abf'
        cook(flat, 'UV Flatten retry (ABF)')
        flat.geometry().saveToFile(cfg['flattened'])
        cook(layout, 'UV Layout retry (ABF, no axis alignment)')
        hou.hipFile.save(cfg['hip'])
    if cfg.get('repairThinFaces') and report['flattenMethod']=='abf':
        original = flat.geometry().freeze()
        ids=set()
        for attempt in range(2):
            bad={t.number() for t in layout.geometry().prims() if uv_area(t)==0}
            if not bad or bad.issubset(ids) or len(ids|bad)>min(32,max(2,len(original.prims())//100)):
                break
            ids.update(bad)
            repaired=repair_uv(original,ids)
            repaired_path=str(Path(cfg['flattened']).with_suffix('.repair.bgeo.sc'))
            repaired.saveToFile(repaired_path)
            fixed=container.createNode('file','repaired_faces')
            fixed.parm('file').set(repaired_path)
            layout.setInput(0,fixed)
            cook(layout,'UV Layout: repack repaired faces '+str(len(ids)))
            hou.hipFile.save(cfg['hip'])
        report['reprojectedFaces']=sorted(ids)
    geo = layout.geometry()
    if len(geo.prims()) != len(source.geometry().prims()):
        raise RuntimeError('UV stage changed primitive count')
    parent = list(range(len(geo.prims())))
    edges, areas, surface_areas = {}, [], []
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for prim in geo.prims():
        vs = prim.vertices()
        coords = [tuple(v.attribValue('uv')[:2]) for v in vs]
        if any(not math.isfinite(x) or x < -1e-5 or x > 1.00001 for uv in coords for x in uv):
            raise RuntimeError('Non-finite or out-of-atlas UV')
        area = uv_area(prim)
        if area <= 0:
            raise RuntimeError('Zero-area UV on %s, face %d after %s layout (axis alignment: %s)' %
                               (prim.attribValue('name'), prim.number(), report['flattenMethod'], layout.parm('axisalignislands').evalAsString()))
        areas.append(area)
        points = [v.point().position() for v in vs]
        surface_areas.append(sum((points[i]-points[0]).cross(points[i+1]-points[0]).length()*.5 for i in range(1,len(points)-1)))
        keys = [(v.point().number(),)+tuple(round(x,7) for x in uv) for v,uv in zip(vs,coords)]
        for i in range(len(keys)):
            key = (prim.attribValue('name'), tuple(sorted((keys[i],keys[(i+1)%len(keys)]))))
            if key in edges:
                parent[root(prim.number())] = root(edges[key])
            else:
                edges[key] = prim.number()
    islands = {}
    for i, area in enumerate(areas):
        entry = islands.setdefault(root(i), [0.,0.])
        entry[0] += area
        entry[1] += surface_areas[i]
    total_surface = sum(surface_areas)
    report.update(islands=len(islands), triangles=len(geo.prims()), uvAreaSum=sum(areas), paddingAtBake=padding,
                  sizes=[], overlapCheck='not performed; packing validity is delegated to UV Layout')
    for size in sorted(set([64,128,256,512,cfg['resolution'],cfg['minimumResolution']])):
        if size > cfg['resolution']:
            continue
        small = [v for v in islands.values() if v[0]*size*size < 1]
        report['sizes'].append({'resolution':size, 'paddingPixels':padding*size/cfg['resolution'],
              'subpixelIslands':len(small), 'subpixelSurfaceFraction':sum(v[1] for v in small)/max(total_surface,1e-30),
              'spacingBudgetSupported':size >= cfg['minimumResolution']})
    geo.saveToFile(cfg['output'])
    atomic(report_path, report)
    smallest = next(x for x in report['sizes'] if x['resolution']==cfg['minimumResolution'])
    if smallest['subpixelIslands']:
        print('UV QUALITY WARNING: %d/%d islands below one pixel at %d; inspect %s before producing smaller textures.' %
              (smallest['subpixelIslands'],len(islands),cfg['minimumResolution'],report_path), flush=True)
    print('UV_COMPLETE '+json.dumps(report['timings']), flush=True)


if __name__ == '__main__':
    try:
        run(sys.argv[1])
    except Exception as error:
        cfg=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        atomic(Path(cfg['report']), {'state':'failed','error':str(error)})
        raise
