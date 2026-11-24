"""Re-read the comments of clips that are still short of their declared count.

One search pass is not enough: TikTok opens the comment panel lazily, so a clip
sometimes reports 0 of 11 and a busy clip stalls at 18 of 49. This re-opens just
the short ones on a second (and third) attempt and rewrites the feed file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, os.path.expanduser('~/.hermes/skills/productivity/tiktok-cdp-search/scripts'))

import tt_run  # noqa: E402
from tt_lib import Tab  # noqa: E402


def main(path, rounds=3):
    rows = [json.loads(l) for l in open(path, encoding='utf-8')]
    tab = Tab('tiktok.com')
    before = sum(len(r.get('comments') or []) for r in rows)
    for attempt in range(1, rounds + 1):
        short = [r for r in rows
                 if len(r.get('comments') or []) < (r.get('comments_declared') or 0)]
        if not short:
            break
        print(f'--- attempt {attempt}: {len(short)} clips short', flush=True)
        for r in short:
            try:
                st = tt_run.comments(tab, r, 100)
            except Exception as e:
                print(f'    WARN {r["url"][:60]}: {e}', flush=True)
                continue
            print(f'    {st} {len(r.get("comments") or []):>3}/'
                  f'{r.get("comments_declared") or 0:<4} {r["url"][-24:]}', flush=True)
            tt_run.save_clips(rows, os.path.basename(path)[len('tiktok_'):-len('.jsonl')])
    after = sum(len(r.get('comments') or []) for r in rows)
    dec = sum(r.get('comments_declared') or 0 for r in rows)
    print(f'\n{os.path.basename(path)}: {before} -> {after} of {dec} '
          f'({round(after / dec * 100) if dec else 0}%)')


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3)
