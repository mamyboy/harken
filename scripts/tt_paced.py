"""Harvest TikTok comments at a human pace, with real gestures.

The earlier failure was not CDP's limits: TikTok answered a burst of ~200 scroll
rounds with a "Please wait..." bot page that renders zero elements, so every
clip looked like it had no comments. This runs one clip at a time, rests between
clips, scrolls with synthesised gestures (the page signs its own next-page
request when it sees a real gesture), and backs off for ten minutes the moment a
challenge appears instead of hammering through it.
"""
import json
import os
import sys
import time

SKILL = os.path.expanduser('~/.hermes/skills/productivity/tiktok-cdp-search/scripts')
sys.path.insert(0, SKILL)
from tt_lib import Tab  # noqa: E402
import tt_run  # noqa: E402

REST_BETWEEN_CLIPS = 75      # seconds: enough that the next page load is not a burst
COOLDOWN_ON_CHALLENGE = 600  # the challenge cleared after ~4 min in testing; be generous
MAX_ROUNDS = 70

# Replies to a comment are a second request (/api/comment/list/reply) that the
# page only fires when someone clicks "View N replies". Analysis needs them: a
# reply often carries the actual objection while the top comment is just bait.
EXPAND_REPLIES = r"""(() => {
  // TikTok marks the link, not the words: element text is Thai ("ดู 1 ความคิดเห็น")
  // or English depending on locale, so matching text missed every one of them.
  const out = [];
  for (const e of document.querySelectorAll('[data-e2e^="comment-reply"]')) {
    if (e.dataset.hkDone) continue;
    e.dataset.hkDone = '1';
    e.click();
    const row = e.closest('[data-e2e="comment-level-1"]');
    out.push(row ? (row.getAttribute('data-cid') || '') : '');
    if (out.length >= 10) break;
  }
  return JSON.stringify(out);
})()"""


def box(tab):
    raw = tab.ev(tt_run.COMMENT_BOX)
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None


def gesture(tab, b, dy=900, mode='wheel'):
    """Scroll the comment list the way a hand does.

    synthesizeScrollGesture sends a whole gesture (with momentum) rather than one
    wheel tick, which is what the virtualised list listens for; the touch drag is
    the mobile-web path and is tried when the mouse gesture yields nothing.
    """
    try:
        if mode == 'gesture':
            # A touch-emulated page rejects a mouse-sourced gesture with -32602,
            # and the previous round's touch attempt leaves emulation on.
            try:
                tab.cdp('Emulation.setTouchEmulationEnabled', enabled=False)
            except Exception:
                pass
            tab.cdp('Input.synthesizeScrollGesture', x=int(b['x']), y=int(b['y']),
                    xDistance=0, yDistance=-int(dy), speed=900,
                    gestureSourceType='mouse', repeatCount=1)
        elif mode == 'touch':
            tab.cdp('Emulation.setTouchEmulationEnabled', enabled=True, maxTouchPoints=1)
            y0, y1 = b['y'] + 180, b['y'] - 180
            tab.cdp('Input.dispatchTouchEvent', type='touchStart',
                    touchPoints=[{'x': b['x'], 'y': y0}])
            for step in range(1, 6):
                tab.cdp('Input.dispatchTouchEvent', type='touchMove',
                        touchPoints=[{'x': b['x'], 'y': y0 + (y1 - y0) * step // 5}])
                time.sleep(0.06)
            tab.cdp('Input.dispatchTouchEvent', type='touchEnd', touchPoints=[])
        else:
            tab.cdp('Input.dispatchMouseEvent', type='mouseWheel', x=b['x'], y=b['y'],
                    deltaX=0, deltaY=dy)
        return True
    except Exception as e:
        print(f'      gesture {mode} failed: {str(e)[:60]}', flush=True)
        return False


def harvest(tab, row, want=100):
    """Read one clip's comments, returning (read, declared, status)."""
    declared = int(row.get('comments_declared') or (row.get('metrics') or {}).get('commentCount') or 0)
    row['comments_declared'] = declared
    tab.goto(row['url'], wait=7)
    if tt_run.interstitial(tab):
        return 0, declared, 'challenge'
    here = tab.ev('location.href') or ''
    if row['id'] not in here:
        return 0, declared, 'not-opened'
    tab.ev(tt_run.OPEN_COMMENTS)
    tab.pump(3.0)

    seen = {}
    idle = 0
    modes = ['gesture', 'touch', 'wheel']
    for rnd in range(1, MAX_ROUNDS + 1):
        before = len(seen)
        for j in tab.take_json('/api/comment/list'):
            for c in j.get('comments') or []:
                u = c.get('user') or {}
                seen[c.get('cid')] = {
                    'user': u.get('nickname') or u.get('unique_id'),
                    'text': c.get('text') or '',
                    'posted_iso': tt_run.ts(c.get('create_time')).isoformat(timespec='minutes')
                    if c.get('create_time') else None,
                    'likes': int(c.get('digg_count') or 0),
                    'replies': int(c.get('reply_comment_total') or 0),
                    'is_author': (u.get('unique_id') or '') == row.get('author'),
                    'stickers_only': not (c.get('text') or '').strip(),
                }
        if declared and len(seen) >= declared:
            break
        if tt_run.interstitial(tab):
            return len(seen), declared, 'challenge'
        b = box(tab)
        if b:
            # cycle the three gesture paths: whichever one the client honours this
            # week keeps the list moving
            gesture(tab, b, 900, modes[rnd % len(modes)])
        idle = idle + 1 if len(seen) == before else 0
        if idle >= 12 and rnd >= 14:
            break
        time.sleep(2.2)

    cs = sorted(seen.values(), key=lambda c: c['posted_iso'] or '', reverse=True)

    # --- replies: click every "View N replies" and read the second endpoint
    want_replies = sum(1 for c in cs if (c.get('replies') or 0) > 0)
    replies = {}
    if want_replies:
        for _ in range(10):
            try:
                clicked = tab.ev(EXPAND_REPLIES)
            except Exception:
                clicked = '[]'
            tab.pump(2.0)
            got_before = len(replies)
            for j in tab.take_json('/api/comment/list/reply'):
                for c in j.get('comments') or []:
                    u = c.get('user') or {}
                    replies[str(c.get('cid'))] = {
                        'parent': str(c.get('reply_id') or c.get('reply_comment_id') or ''),
                        'user': u.get('nickname') or u.get('unique_id'),
                        'text': c.get('text') or '',
                        'posted_iso': tt_run.ts(c.get('create_time')).isoformat(timespec='minutes')
                        if c.get('create_time') else None,
                        'likes': int(c.get('digg_count') or 0),
                        'is_author': (u.get('unique_id') or '') == row.get('author'),
                    }
            if len(replies) == got_before and clicked in ('[]', '', None):
                break
            if len(replies) >= sum(c.get('replies') or 0 for c in cs):
                break

    prev = row.get('comments') or []
    merged = [dict(c) for c in cs]
    by_parent = {}
    for cid, r in replies.items():
        by_parent.setdefault(r['parent'], []).append(r)
    flat = list(merged)
    for cid, rs in by_parent.items():
        for r in rs:
            flat.append({'user': r['user'], 'text': r['text'], 'posted_iso': r['posted_iso'],
                         'likes': r['likes'], 'replies': 0, 'is_author': r['is_author'],
                         'is_reply': True, 'parent': cid, 'stickers_only': not r['text'].strip()})
    if len(flat) >= len(prev):
        row['comments'] = flat[:want] if want else flat
    row['comments_seen'] = max(len(flat), len(prev))
    row['replies_read'] = len(replies)
    row['replies_declared'] = want_replies
    return len(row.get('comments') or []), declared, 'ok'


def main(path, rounds=2):
    rows = [json.loads(l) for l in open(path, encoding='utf-8')]
    name = os.path.basename(path)[len('tiktok_'):-len('.jsonl')]
    print(f'{os.path.basename(path)}: {len(rows)} clips', flush=True)
    for attempt in range(1, rounds + 1):
        short = [r for r in rows
                 if len(r.get('comments') or []) < (r.get('comments_declared') or 0)]
        if not short:
            break
        print(f'\n=== attempt {attempt}: {len(short)} clips short', flush=True)
        for i, r in enumerate(short):
            try:
                got, dec, st = harvest(tab := Tab('tiktok.com'), r)
            except Exception as e:
                print(f'  WARN {r["url"][-24:]}: {str(e)[:70]}', flush=True)
                continue
            print(f'  {st:<10} {got:>3}/{dec:<4} {r["url"][-24:]}', flush=True)
            tt_run.save_clips(rows, name)
            if st == 'challenge':
                print(f'  ...bot challenge: resting {COOLDOWN_ON_CHALLENGE // 60} min', flush=True)
                time.sleep(COOLDOWN_ON_CHALLENGE)
            elif i < len(short) - 1:
                time.sleep(REST_BETWEEN_CLIPS)

    got = sum(len(r.get('comments') or []) for r in rows)
    dec = sum(r.get('comments_declared') or 0 for r in rows)
    print(f'\n{os.path.basename(path)}: {got}/{dec} ({round(got / dec * 100) if dec else 0}%)', flush=True)


if __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2)
