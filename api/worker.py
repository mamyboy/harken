"""Pipeline worker — ingest, translate, score and filter feeds outside the API.

Running this in its own launchd job means restarting or redeploying the web app
never interrupts a half-finished ingest or LLM call, and only one writer ever
touches the database (guarded by a lock file).
"""
import asyncio
import fcntl
import os
import sys
import time

from . import db, ingest as ingest_mod, insight, sentiment as sentiment_mod, translate as translate_mod

PROJECT = os.path.expanduser('~/Projects/harken')
TICK = float(os.environ.get('HARKEN_INGEST_SECONDS', '3'))
CATCHUP = float(os.environ.get('HARKEN_CATCHUP_SECONDS', '60'))
LOCK = os.path.expanduser('~/Projects/harken/.worker.lock')


def _acquire_lock():
    fh = open(LOCK, 'w')
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print('[worker] another worker holds the lock — exiting', flush=True)
        sys.exit(0)
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def cycle(analyze=True):
    """One ingest→analyse pass. Returns a dict for logging/assertions."""
    out = {}
    try:
        out['ingest'] = ingest_mod.ingest(project=os.environ.get('HARKEN_FEEDS', PROJECT))
    except Exception as e:
        out['ingest_error'] = '%s: %s' % (type(e).__name__, e)
    if not analyze:
        return out
    for name, fn, key in (('translate', translate_mod.translate_pending, 'pending'),
                          ('sentiment', sentiment_mod.run, 'pending'),
                          ('sentiment:comments', sentiment_mod.run_comments, 'pending'),
                          ('relevance', insight.run_relevance, 'checked')):
        try:
            res = fn()
            if res.get(key):
                out[name] = res
        except Exception as e:
            out[name + '_error'] = '%s: %s' % (type(e).__name__, e)
    return out


async def loop():
    last_fp = None
    last_catchup = time.time()
    while True:
        try:
            fp = ingest_mod.fingerprint()
            if fp != last_fp:
                last_fp = fp
                last_catchup = time.time()
                res = await asyncio.to_thread(cycle)
                if res:
                    print('[worker] %s -> %s' % (time.strftime('%H:%M:%S'), res), flush=True)
            elif time.time() - last_catchup >= CATCHUP:
                # translations left over from a big batch used to wait for the NEXT
                # feed file; keep draining them on a timer instead
                last_catchup = time.time()
                if translate_mod.pending(limit=1):
                    res = await asyncio.to_thread(translate_mod.translate_pending)
                    print('[worker] %s catch-up translate -> %s' % (time.strftime('%H:%M:%S'), res),
                          flush=True)
        except Exception as e:
            print('[worker] error %s: %s' % (type(e).__name__, e), flush=True)
        await asyncio.sleep(TICK)


def main():
    fh = _acquire_lock()
    db.init()
    print('[worker] started pid=%s tick=%ss' % (os.getpid(), TICK), flush=True)
    try:
        asyncio.run(loop())
    except KeyboardInterrupt:
        pass
    finally:
        fh.close()


if __name__ == '__main__':
    main()
