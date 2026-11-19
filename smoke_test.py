import importlib.util
import json
import math
import sys
from pathlib import Path

folder = Path(__file__).parent / 'Tests' / 'GeometrySmoke'
folder.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('builder', str(Path(__file__).parent / 'build_proxy.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
positions, normals, uv, triangles = [], [], [], []
size = 24
for y in range(size + 1):
    for x in range(size + 1):
        positions.append(dict(x=x / size, y=0.0, z=y / size))
        normals.append(dict(x=0.0, y=1.0, z=0.0))
        uv.append(dict(x=x / size, y=y / size))
for y in range(size):
    for x in range(size):
        a = y * (size + 1) + x
        triangles.extend([a, a + size + 1, a + 1, a + 1, a + size + 1, a + size + 2])
part = dict(material=0, positions=positions, normals=normals, uv=uv, triangles=triangles)
job = dict(version=1, percentage=35, parts=[part, dict(part, material=1)])
path = folder / 'job.json'
path.write_text(json.dumps(job))
module.build(str(path))
result = json.loads((folder / 'result.json').read_text())
assert result['outputTriangles'] < result['inputTriangles']
assert [p['material'] for p in result['parts']] == [0, 1]
for p in result['parts']:
    assert len(p['positions']) == len(p['normals']) == len(p['uv'])
    assert all(0 <= i < len(p['positions']) for i in p['triangles'])
    assert all(abs(v['y']) < 1e-6 for v in p['positions'])
    assert all(abs(n['y'] - 1) < 1e-6 for n in p['normals'])
    assert all(-1e-6 <= v[k] <= 1.000001 for v in p['uv'] for k in ('x','y'))
print('PASS: reduction, material IDs, bounds, UV, normals and indices', result['inputTriangles'], result['outputTriangles'])
