"""Non-critical UI progress. Bake outputs and checkpoints use strict writes."""
import errno
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

_warn_after = 0.0


def cache_sources(builder, worker):
    sources = [builder.read_bytes(), worker.read_bytes() if worker.exists() else b'']
    history = [('60700ec72f1a290ce3c03350660302ac203f4906322130a3b2e189912779959b', 'resume_v2_builder.txt', '0ffd20a963be00a57d7f00134e1da1af97e42101c7292c9f1ff70b85d023f84e'),
               ('a317e23389564693167db4fb9254fc8956f880c14884a7f3ccfc19bcf692e0a0', 'uv_layout_v2_worker.txt', 'da5e762ba35728268db95206947e90eb64e3c2d3edffcf1fdc0a30ff75427e88')]
    if all(hashlib.sha256(data).hexdigest() == new for data,(new,_,_) in zip(sources,history)):
        previous = [builder.with_name(name).read_bytes() for _,name,_ in history]
        if all(hashlib.sha256(data).hexdigest() == old for data,(_,_,old) in zip(previous,history)):
            return previous
        raise ValueError('HLOD cache compatibility files do not match the installed version')
    return sources


def sharing_error(exc):
    return getattr(exc,'winerror',None) in (5,32,33) or (os.name=='nt' and exc.errno==errno.EACCES)


def warn(path, exc):
    global _warn_after
    if time.monotonic() >= _warn_after:
        print('PROGRESS_BUSY: UI update skipped; build continues: %s (%s)' % (path,exc), flush=True)
        _warn_after = time.monotonic()+5


def read_progress(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except OSError as exc:
        if not sharing_error(exc):
            raise
        warn(path,exc)
        return None


def publish(path, state):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.progress-',suffix='.tmp',
                                         mode='w',encoding='utf-8',delete=False) as stream:
            temp = Path(stream.name)
            json.dump(state,stream,allow_nan=False)
        for delay in (0,.01,.025,.06,.12):
            if delay: time.sleep(delay)
            try:
                os.replace(temp,path)
                return True
            except OSError as exc:
                if not sharing_error(exc): raise
                last = exc
        warn(path,last)
        return False
    finally:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError as exc:
                if not sharing_error(exc): raise

