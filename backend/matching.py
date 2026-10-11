"""Bounded observation matching; no detector results are synthesized here."""

from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class MatchSettings:
    max_cost: float = 0.42
    min_visual_similarity: float = 0.65
    max_area_ratio: float = 3.0
    movement_threshold: float = 0.06
    ambiguity_margin: float = 0.04


def evidence(before, after):
    visual = float(np.clip(np.dot(before['embedding'], after['embedding']), -1, 1))
    color = float(np.clip(np.sqrt(np.asarray(before['color']) * after['color']).sum(), 0, 1))
    distance = math.dist(before['center'], after['center'])
    ratio = max(before['area'], after['area']) / max(min(before['area'], after['area']), 1e-8)
    cost = 0.50 * (1 - visual) + 0.25 * (1 - color)
    cost += 0.10 * min(distance / 0.5, 1) + 0.15 * min(abs(math.log(ratio)), 1)
    return dict(cost=cost, visual_similarity=visual, color_similarity=color,
                displacement=distance, area_ratio=ratio)


def public_object(obj):
    return {key: value for key, value in obj.items() if key not in ('embedding', 'color')}


def compare(before, after, settings=MatchSettings()):
    n, m = len(before), len(after)
    # Explicit unmatched slots avoid forcing poor matches in equal-sized scenes.
    costs = np.full((n + m, n + m), 1e6, dtype=float)
    costs[:n, m:] = settings.max_cost / 2
    costs[n:, :m] = settings.max_cost / 2
    costs[n:, m:] = 0
    pairs = {}
    for i, old in enumerate(before):
        for j, new in enumerate(after):
            if old['label'] != new['label']:
                continue
            metrics = evidence(old, new)
            if metrics['visual_similarity'] < settings.min_visual_similarity:
                continue
            if metrics['area_ratio'] > settings.max_area_ratio:
                continue
            if metrics['cost'] >= settings.max_cost:
                continue
            pairs[i, j] = metrics
            costs[i, j] = metrics['cost']
    rows, cols = linear_sum_assignment(costs)
    matched_old, matched_new, events = set(), set(), []
    for i, j in zip(rows.tolist(), cols.tolist()):
        if (i, j) not in pairs:
            continue
        metrics = pairs[i, j]
        alternatives = [v['cost'] for (a, b), v in pairs.items()
                        if (a == i or b == j) and (a, b) != (i, j)]
        margin = min(alternatives, default=1.0) - metrics['cost']
        uncertain = margin < settings.ambiguity_margin
        kind = 'MOVED' if metrics['displacement'] > settings.movement_threshold else 'UNCHANGED'
        events.append(dict(type=kind, before=public_object(before[i]),
                           after=public_object(after[j]), evidence=metrics,
                           matching_score=1 - metrics['cost'],
                           needs_review=uncertain, alternative_cost_margin=margin))
        matched_old.add(i)
        matched_new.add(j)
    for i, obj in enumerate(before):
        if i not in matched_old:
            events.append(dict(type='REMOVED', before=public_object(obj), after=None,
                               needs_review=True, reason='Not detected or confidently matched in second image'))
    for j, obj in enumerate(after):
        if j not in matched_new:
            events.append(dict(type='ADDED', before=None, after=public_object(obj),
                               needs_review=True, reason='No confident match in first image'))
    return dict(counts={kind: sum(e['type'] == kind for e in events)
                        for kind in ('ADDED', 'REMOVED', 'MOVED', 'UNCHANGED')},
                events=events, requires_review=any(e['needs_review'] for e in events))
