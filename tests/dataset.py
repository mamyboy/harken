#!/usr/bin/python3
"""Is the dashboard holding any posts at all?

Several suites assert on ink that only exists when the dataset is non-empty: a
donut with slices, a trend line, an appbar counter that is not '0 โพสต์'. Run
against a deliberately cleared database they go red for a reason that has
nothing to do with the code, which teaches everyone to ignore red.

Those checks ask this module first and print SKIP instead. A skip is loud on
purpose -- it is not a pass, it just means this dataset cannot answer.
"""
import json
import urllib.request

BASE = 'http://localhost:8000'


def empty(base=BASE):
    """True when /api/stats reports no posts (or the app is unreachable)."""
    try:
        with urllib.request.urlopen(base + '/api/stats', timeout=10) as fh:
            d = json.load(fh)
    except Exception:
        return True
    total = d.get('total')
    if total is None:
        total = d.get('posts') or 0
    return int(total) == 0


def skip(name, why='no posts in the dataset yet'):
    print(f'SKIP  {name}  {why}')
