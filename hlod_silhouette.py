"""Compare orthographic triangle coverage before accepting reduction of a source part."""
import numpy as np
from PIL import Image, ImageDraw

def triangles(geo):
    xyz=np.asarray(geo.pointFloatAttribValues('P'),dtype=np.float64).reshape(-1,3)
    return xyz[np.asarray([[v.point().number() for v in t.vertices()] for t in geo.prims()],dtype=np.intp)]

def masks(tris,frames):
    result=[]
    for axes,origin,scale in frames:
        img=Image.new('1',(128,128))
        draw=ImageDraw.Draw(img)
        for t in ((tris[:,:,axes]-origin)*scale+2).astype(np.int32):
            draw.polygon([tuple(q) for q in t],fill=1)
        result.append(np.array(img))
    return result

def choose(parent,source,percentage,name,reduce,checked):
    high=triangles(source.geometry());frames=[]
    for axes in ([0,1],[0,2],[1,2]):
        pos=high[:,:,axes].reshape(-1,2); lo=pos.min(axis=0);span=(pos.max(axis=0)-lo).max()
        frames.append((axes,lo,123/max(span,1e-10)))
    reference=masks(high,frames)
    node=reduce(parent,source,percentage,name)
    reducer=node.inputs()[0]
    for factor in (percentage,(100+percentage)/2,(300+percentage)/4):
        reducer.parm('percentage').set(factor)
        candidate=masks(triangles(checked(node)),frames)
        loss=max(np.count_nonzero(a & ~b)/max(1,np.count_nonzero(a)) for a,b in zip(reference,candidate))
        if loss<=.05:
            if factor!=percentage:print('SILHOUETTE: %s %.1f%% -> %.1f%%, max loss %.1f%%'%(name,percentage,factor,loss*100),flush=True)
            return node,factor
    print('SILHOUETTE: %s kept source geometry to preserve coverage'%name,flush=True)
    return source,100.

