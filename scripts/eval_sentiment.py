#!/usr/bin/env python3
"""What are the sentiment labels actually worth?

`sentiment_v1.json` is 60 hand-authored sentences with a human label. Running the
real classifier over them answers three questions the dashboard cannot:

  1. per-class precision / recall on the three poles the charts draw
  2. how well the specific emotion matches the category the author gave it
  3. **calibration** -- when the model says 0.85, how often is it right? If the
     accuracy of the 0.5-0.7 bucket is as high as the 0.9+ bucket, the
     confidence number is decoration and the UI must stop trusting it.

Writes reports/sentiment_eval.json so a later run can be diffed against this one.
"""
import json
import os
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)          # `api` is a package at the project root

from api import sentiment as S, llm  # noqa: E402

GOLD = os.path.join(ROOT, 'src', 'harken', 'evaluation', 'sentiment_v1.json')
OUT = os.path.join(ROOT, 'reports', 'sentiment_eval.json')
# --set picks another labelled file; the real comments set is the hard one.
import argparse
CHUNK = 15

LABEL_MAP = {'positive': 'pos', 'negative': 'neg', 'neutral': 'neu', 'mixed': 'neu'}
CAT_EMOTION = {'praise': 'praise', 'complaint': 'disappointment', 'anger': 'anger',
               'fear': 'fear', 'mockery': 'mockery', 'sarcasm': 'mockery',
               'neutral': 'neutral', 'disappointment': 'disappointment'}
BUCKETS = [(0.0, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01)]


def load(path=GOLD):
    d = json.load(open(path, encoding='utf-8'))
    out = []
    for e in d['examples']:
        raw = str(e.get('label', '')).strip().lower()
        lab = LABEL_MAP.get(raw) or (raw if raw in ('pos', 'neu', 'neg') else None)
        if not lab:
            continue
        out.append({'id': e['id'], 'text': e['text'], 'label': lab,
                    'category': (str(e.get('category') or '').strip().lower()
                                 or str(e.get('emotion') or '').strip().lower()),
                    # hand-labelled sarcasm, when the file carries it
                    'sarcasm_gold': (None if e.get('sarcasm') is None else int(e['sarcasm']))})
    return out


def classify_all(examples):
    session = llm.new_session('harken-eval')
    rows, got = [], 0
    for i in range(0, len(examples), CHUNK):
        chunk = examples[i:i + CHUNK]
        items = [{'text_raw': c['text']} for c in chunk]
        preds = S._classify(session, items, 'text_raw')
        by_text = {p[0]: p for p in preds}
        for c in chunk:
            p = by_text.get(c['text'])
            rows.append({'id': c['id'], 'label': c['label'], 'category': c['category'],
                         'sarcasm_gold': c.get('sarcasm_gold'),
                         'pred': (p[1] if p else None),
                         'conf': (p[2] if p else 0.0),
                         'emotion': (p[4] if p else None),
                         'polarity': (p[5] if p else None),
                         'sarcasm': (p[6] if p else 0),
                         'why': (p[3] if p else '')})
            got += 1 if p else 0
        print(f'  chunk {i // CHUNK + 1}: {len(chunk)} sentences, {got}/{len(rows)} parsed', flush=True)
    return rows


def metrics(rows):
    labels = ('pos', 'neu', 'neg')
    tp = Counter()
    fp = Counter()
    fn = Counter()
    for r in rows:
        if not r['pred']:
            fn[r['label']] += 1
            continue
        if r['pred'] == r['label']:
            tp[r['pred']] += 1
        else:
            fp[r['pred']] += 1
            fn[r['label']] += 1
    per = {}
    for lab in labels:
        p = tp[lab] / (tp[lab] + fp[lab]) if tp[lab] + fp[lab] else 0.0
        rec = tp[lab] / (tp[lab] + fn[lab]) if tp[lab] + fn[lab] else 0.0
        f1 = 2 * p * rec / (p + rec) if p + rec else 0.0
        per[lab] = {'precision': round(p, 3), 'recall': round(rec, 3), 'f1': round(f1, 3),
                    'support': tp[lab] + fn[lab]}
    correct = sum(1 for r in rows if r['pred'] == r['label'])
    acc = correct / len(rows) if rows else 0.0
    conf = [[sum(1 for r in rows if r['label'] == a and r['pred'] == b)
             for b in labels] for a in labels]
    return per, round(acc, 3), conf


def calibration(rows):
    out = []
    for lo, hi in BUCKETS:
        sel = [r for r in rows if r['pred'] and lo <= r['conf'] < hi]
        if not sel:
            out.append({'conf': f'{lo:.2f}-{hi:.2f}', 'n': 0, 'accuracy': None})
            continue
        acc = sum(1 for r in sel if r['pred'] == r['label']) / len(sel)
        out.append({'conf': f'{lo:.2f}-{hi:.2f}', 'n': len(sel),
                    'accuracy': round(acc, 3),
                    'mean_conf': round(sum(r['conf'] for r in sel) / len(sel), 3)})
    # one number that says whether the confidence is informative at all
    pairs = [(r['conf'], 1 if r['pred'] == r['label'] else 0) for r in rows if r['pred']]
    gap = None
    hi_sel = [c for c, ok in pairs if c >= 0.7]
    lo_sel = [ok for c, ok in pairs if c < 0.7]
    if hi_sel and lo_sel:
        gap = round(sum(1 for c in hi_sel if True) / max(1, len(hi_sel)) - sum(lo_sel) / len(lo_sel), 3)
        acc_hi = sum(ok for c, ok in pairs if c >= 0.7) / len(hi_sel)
        gap = round(acc_hi - sum(lo_sel) / len(lo_sel), 3)
    return out, gap


def emotion_check(rows):
    pairs = [(r, CAT_EMOTION.get(r['category'])) for r in rows]
    pairs = [(r, want) for r, want in pairs if want]
    if not pairs:
        return {'n': 0}
    hit = sum(1 for r, want in pairs if r['emotion'] == want)
    per = defaultdict(lambda: {'n': 0, 'hit': 0})
    for r, want in pairs:
        per[want]['n'] += 1
        if r['emotion'] == want:
            per[want]['hit'] += 1
    return {'n': len(pairs), 'accuracy': round(hit / len(pairs), 3),
            'per_emotion': {k: {'n': v['n'], 'accuracy': round(v['hit'] / v['n'], 3)}
                            for k, v in sorted(per.items())}}


def sarcasm_check(rows):
    pairs = [(r['sarcasm_gold'], r['sarcasm']) for r in rows
             if r.get('sarcasm_gold') is not None and r['pred']]
    if not pairs:
        return {'n': 0}
    tp = sum(1 for want, got in pairs if want == 1 and got == 1)
    fp = sum(1 for want, got in pairs if want == 0 and got == 1)
    fn = sum(1 for want, got in pairs if want == 1 and got == 0)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {'n': len(pairs), 'gold_positive': tp + fn, 'precision': round(prec, 3),
            'recall': round(rec, 3), 'flagged': tp + fp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', default=GOLD, help='labelled file to measure against')
    ap.add_argument('--out', default=OUT, help='where the JSON report lands')
    args = ap.parse_args()
    t0 = time.time()
    examples = load(args.set)
    print(f'eval: {len(examples)} labelled sentences from {os.path.basename(args.set)}')
    print('labels:', dict(Counter(e['label'] for e in examples)))
    rows = classify_all(examples)
    parsed = [r for r in rows if r['pred']]
    if not parsed:
        print('nothing parsed -- the local model did not answer; no numbers to report')
        return 1
    per, acc, conf = metrics(rows)
    cal, gap = calibration(rows)
    emo = emotion_check(rows)
    sarc = sarcasm_check(rows)
    report = {'dataset': os.path.basename(args.set), 'n': len(rows), 'parsed': len(parsed),
              'accuracy': acc, 'per_class': per,
              'confusion': {'rows': ['pos', 'neu', 'neg'], 'cols': ['pos', 'neu', 'neg'],
                            'matrix': conf},
              'calibration': cal, 'confidence_gap': gap,
              'emotion': emo, 'sarcasm': sarc, 'seconds': round(time.time() - t0),
              'model': S.MODEL, 'sarcasm_flagged': sum(1 for r in parsed if r['sarcasm'])}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(report, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print(f'\naccuracy {acc:.3f} on {len(parsed)}/{len(rows)} parsed')
    for lab, m in per.items():
        print(f"  {lab}: P {m['precision']:.2f} R {m['recall']:.2f} F1 {m['f1']:.2f}  (n={m['support']})")
    print('  confusion (row=truth, col=pred):', conf)
    print('\ncalibration:')
    for b in cal:
        if b['n']:
            print(f"  conf {b['conf']}: n={b['n']:<3} accuracy={b['accuracy']:.2f} (claimed {b['mean_conf']:.2f})")
    print(f"\nconfidence gap (>=0.70 minus <0.70): {gap}")
    print(f"emotion: {emo.get('accuracy')} on n={emo.get('n')}  sarcasm flagged: {report['sarcasm_flagged']}")
    if sarc.get('n'):
        print(f"sarcasm: P {sarc['precision']:.2f} R {sarc['recall']:.2f} "
              f"(gold +{sarc['gold_positive']}, flagged {sarc['flagged']}, n={sarc['n']})")
    print(f'report: {args.out}  ({report["seconds"]}s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
