#!/usr/bin/env python3
"""Spot-check sentiment labels against simple lexical expectations.

Flags: posts labelled pos that contain strong negative cues, and vice versa.
Not a ground-truth benchmark — a triage signal for where the classifier drifts.
"""
import os
import re
import sqlite3

DB = os.path.expanduser('~/Projects/harken/harken.db')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

NEG = ['ไม่ดี', 'แย่มาก', 'ผิดหวัง', 'โกรธ', 'ประณาม', 'วิกฤต', 'ล้มเหลว',
       'ไม่จับมือ', 'ขัดแย้ง', 'ไม่เห็นด้วย', 'ซัด', 'จี้', 'ฮุบ', 'สวนหมัด', 'ตึงเครียด']
POS = ['ดีมาก', 'ยินดี', 'ชื่นชม', 'ขอบคุณ', 'ยอดเยี่ยม', 'สำเร็จ', 'ร่วมมือ', 'เห็นด้วย',
       'โปรดปราน', 'ชื่นชอบ', 'น่าภูมิใจ']

# phrases where a cue word is negated or reversed (Thai has no word boundaries,
# so plain substring hits generate false alarms)
NEGATED = {'ตึงเครียด': ['ลดความตึงเครียด', 'คลี่คลายความตึงเครียด', 'ผ่อนคลายความตึงเครียด']}

rows = conn.execute(
    "SELECT author, text_th, text_raw, sentiment, likes FROM posts "
    "WHERE sentiment IN ('pos','neg') ORDER BY posted_iso DESC").fetchall()


def text(r):
    return (r['text_th'] or r['text_raw'] or '')


def cues(text_, words):
    """Cue hits, ignoring occurrences that sit inside a reversing phrase."""
    hits = []
    for w in words:
        idx = text_.find(w)
        if idx < 0:
            continue
        if any(text_[max(0, idx - len(p) + len(w)):idx + len(w)] == p
               for p in NEGATED.get(w, [])):
            continue
        hits.append(w)
    return hits


flagged = []
for r in rows:
    t = text(r)
    if r['sentiment'] == 'pos' and cues(t, NEG):
        flagged.append(('pos→neg', r, cues(t, NEG)))
    if r['sentiment'] == 'neg' and cues(t, POS):
        flagged.append(('neg→pos', r, cues(t, POS)))

print('labelled pos/neg posts:', len(rows))
print('flagged for manual review:', len(flagged))
print()
for tag, r, hits in flagged[:8]:
    print(f"[{tag}] cues={hits} @{r['author']}  ({r['likes']} likes)")
    print('   ', text(r)[:150].replace('\n', ' '))
    print()

# label distribution + coverage of translation
dist = {k: v for k, v in conn.execute(
    "SELECT COALESCE(NULLIF(sentiment,''),'none') s, COUNT(*) n FROM posts GROUP BY s")}
print('distribution:', dist)
missing = conn.execute(
    "SELECT COUNT(*) c FROM posts WHERE COALESCE(sentiment,'') = ''").fetchone()['c']
untranslated = conn.execute(
    "SELECT COUNT(*) c FROM posts WHERE COALESCE(text_th,'') = ''").fetchone()['c']
print('unlabelled posts:', missing, '| untranslated posts:', untranslated)
