"""Fuzzy regression-discontinuity estimator for actual tutoring participation.

The running variable is the enrolment score.  Eligibility is deterministic in
the enrolment score and the batch threshold.  Actual participation is recorded
separately, so the causal parameter is a local average treatment effect (LATE)
for compliers at the threshold, obtained with a just-identified 2SLS local
linear specification on a triangular kernel window.

Bandwidth rule (``auto_min_side_n``) looks only at enrolment scores (and the
number of roster members on each side).  It never inspects the final course
score.  This keeps the window ex-ante with respect to the outcome.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy import stats

IDENTIFICATION_ASSUMPTIONS = [
    '入学分不可被个人精确操纵，断点两侧学员在研究变量上连续可比。',
    '除实际参辅外，断点处的其他因素与结课成绩之间没有跳跃。',
    '实际参辅对入学分是单调的：越线只可能提高参辅概率，不排斥任何一名学员。',
    '排除性约束：资格（越线）只通过实际参辅影响结课成绩。',
    '局部效应仅适用于断点附近带宽内的合规者，不能外推到全体学员。',
]


def signed_distance(score: float, threshold: float, direction: str) -> float:
    """Running variable u with eligibility at u >= 0."""
    return score - threshold if direction == 'gte' else threshold - score


def is_eligible(score: float, threshold: float, direction: str) -> bool:
    return score >= threshold if direction == 'gte' else score <= threshold


def choose_bandwidth(scores: Iterable[float], threshold: float, direction: str,
                     rule: str = 'auto_min_side_n', manual: float | None = None,
                     min_side_n: int = 5, min_side_distinct: int = 5) -> dict:
    """Pick a symmetric window using enrolment scores only.

    Returns a dict with ``bandwidth`` (None when no admissible window exists)
    and a transparent ``basis`` used by the UI and the report export.
    """
    distances = sorted({abs(signed_distance(float(s), threshold, direction)) for s in scores})
    basis = {
        'rule': rule,
        'uses_outcome': False,
        'uses_final_score': False,
        'min_side_n': min_side_n,
        'min_side_distinct': min_side_distinct,
        'threshold': threshold,
        'direction': direction,
    }
    if rule == 'manual':
        h = float(manual) if manual else None
        basis.update({'manual_bandwidth': h, 'reason': 'manual rule; chosen without final scores'})
        if h is None:
            return {'bandwidth': None, 'basis': basis, 'diagnostics': {}}
        diagnostics = _window_diagnostics(scores, threshold, direction, h)
        basis.update(diagnostics)
        basis['admissible'] = diagnostics['left_n'] >= min_side_n and diagnostics['right_n'] >= min_side_n
        return {'bandwidth': h if basis['admissible'] else None, 'basis': basis, 'diagnostics': diagnostics}

    candidates = [d for d in distances if d > 0]
    for h in candidates:
        diagnostics = _window_diagnostics(scores, threshold, direction, h)
        if (diagnostics['left_n'] >= min_side_n and diagnostics['right_n'] >= min_side_n
                and diagnostics['left_distinct'] >= min_side_distinct
                and diagnostics['right_distinct'] >= min_side_distinct):
            basis.update(diagnostics)
            basis['admissible'] = True
            basis['reason'] = ('expand symmetrically from the threshold until both sides have at least '
                               f'{min_side_n} roster members and {min_side_distinct} distinct enrolment scores; '
                               'final scores are not used')
            return {'bandwidth': h, 'basis': basis, 'diagnostics': diagnostics}
    # No window satisfies the rule: still report the widest window's diagnostics.
    widest = candidates[-1] if candidates else 0.0
    diagnostics = _window_diagnostics(scores, threshold, direction, widest)
    basis.update(diagnostics)
    basis['admissible'] = False
    basis['reason'] = 'no symmetric window satisfies the minimum side counts/distinct scores'
    return {'bandwidth': None, 'basis': basis, 'diagnostics': diagnostics}


def _window_diagnostics(scores, threshold, direction, h) -> dict:
    left = [s for s in scores if signed_distance(float(s), threshold, direction) < 0
            and abs(signed_distance(float(s), threshold, direction)) <= h]
    right = [s for s in scores if signed_distance(float(s), threshold, direction) >= 0
             and abs(signed_distance(float(s), threshold, direction)) <= h]
    return {
        'left_n': len(left),
        'right_n': len(right),
        'left_distinct': len({round(float(s), 6) for s in left}),
        'right_distinct': len({round(float(s), 6) for s in right}),
    }


def _weighted_ls(y: np.ndarray, x: np.ndarray, w: np.ndarray):
    sw = np.sqrt(w)
    xw, yw = x * sw[:, None], y * sw
    xtx_inv = np.linalg.pinv(xw.T @ xw)
    beta = xtx_inv @ (xw.T @ yw)
    resid = yw - xw @ beta
    n, k = xw.shape
    meat = (xw * (resid ** 2)[:, None]).T @ xw
    cov = xtx_inv @ meat @ xtx_inv * (n / max(n - k, 1))
    return beta, cov, resid


def _ols_jump(y, x, z, w):
    beta, cov, resid = _weighted_ls(y, x, w)
    se = math.sqrt(max(cov[3, 3], 0.0))
    return {'jump': float(beta[3]), 'se': se,
            'ci_low': float(beta[3] - stats.t.ppf(.975, max(len(y) - 4, 1)) * se),
            'ci_high': float(beta[3] + stats.t.ppf(.975, max(len(y) - 4, 1)) * se),
            't': float(beta[3] / se) if se > 0 else None}


def fuzzy_local_rd(rows: list[dict], threshold: float, direction: str, bandwidth: float,
                   min_participation_jump: float = .2, kernel: str = 'triangular') -> dict:
    """Estimate the LATE of participation at the threshold.

    ``rows`` items: code, enrollment_score, participated, outcome, eligible.
    """
    window = []
    for r in rows:
        u = signed_distance(float(r['enrollment_score']), threshold, direction)
        if abs(u) <= bandwidth:
            window.append({**r, 'u': u})
    window.sort(key=lambda r: (r['u'], r['code']))

    n = len(window)
    if n < 8:
        return {'status': 'inconclusive', 'reason': '带宽内有效观测不足（少于 8 条），拒绝给出因果结论',
                'assumptions': IDENTIFICATION_ASSUMPTIONS, 'window_n': n, 'checks': {'min_n': False}}

    u = np.array([r['u'] for r in window], dtype=float)
    z = (u >= 0).astype(float)
    p = np.array([1.0 if r['participated'] else 0.0 for r in window])
    y = np.array([float(r['outcome']) for r in window])
    if kernel == 'triangular':
        w = np.maximum(0.0, 1.0 - np.abs(u) / bandwidth)
        keep = w > 0
    elif kernel == 'uniform':
        w = np.ones_like(u)
        keep = np.ones_like(u, dtype=bool)
    else:
        raise ValueError(f'未知核函数 {kernel}')
    if not keep.all():
        window = [r for r, k in zip(window, keep) if k]
        u, z, p, y, w = u[keep], z[keep], p[keep], y[keep], w[keep]
        n = len(window)

    eligible_mismatch = sum(1 for i, r in enumerate(window) if bool(r.get('eligible')) != bool(z[i]))
    left, right = z == 0, z == 1
    if left.sum() < 2 or right.sum() < 2:
        return {'status': 'inconclusive', 'reason': '断点任一侧有效观测不足 2 条，无法做局部线性估计',
                'assumptions': IDENTIFICATION_ASSUMPTIONS, 'window_n': n,
                'checks': {'min_n': False}}

    distinct_left = len({round(float(v), 6) for v in u[left]})
    distinct_right = len({round(float(v), 6) for v in u[right]})
    mass_at_cutoff = float(np.mean(u == 0))
    discrete_reasons = []
    if distinct_left < 3 or distinct_right < 3:
        discrete_reasons.append(f'断点两侧入学分取值过少（左 {distinct_left} / 右 {distinct_right} 个不同值）')
    if mass_at_cutoff > 0.2:
        discrete_reasons.append(f'恰好落在门槛上的样本占比 {mass_at_cutoff:.0%}，存在质量点')

    # Design matrices: side-specific intercept/slope plus the eligibility jump.
    x_base = np.column_stack([np.ones(n), u, u * z])
    x_first = np.column_stack([x_base, z])
    first = _ols_jump(p, x_first, z, w)
    reduced = _ols_jump(y, x_first, z, w)

    # Structural equation: y = a + b*u + c*u*z + tau*P, instrumented by z.
    xe = np.column_stack([x_base, p])
    zi = x_first
    sw = np.sqrt(w)
    xew, ziw, yw = xe * sw[:, None], zi * sw[:, None], y * sw
    proj = ziw @ np.linalg.pinv(ziw.T @ ziw) @ ziw.T
    xhat = proj @ xew
    xtx_inv = np.linalg.pinv(xhat.T @ xhat)
    beta = xtx_inv @ (xhat.T @ yw)
    resid = yw - xew @ beta
    meat = (xhat * (resid ** 2)[:, None]).T @ xhat
    cov = xtx_inv @ meat @ xtx_inv * (n / max(n - 4, 1))
    tau = float(beta[3])
    se = math.sqrt(max(cov[3, 3], 0.0))
    df = max(n - 4, 1)
    crit = float(stats.t.ppf(.975, df))
    ci_low, ci_high = tau - crit * se, tau + crit * se
    p_value = float(2 * stats.t.sf(abs(tau / se), df)) if se > 0 else None

    perfect_compliance = first['se'] <= 1e-12
    first_stage_F = (first['jump'] / first['se']) ** 2 if first['se'] > 0 else float('inf')
    checks = {
        'min_n': True,
        'sharp_design': bool(perfect_compliance),
        'scores_not_discrete': not discrete_reasons,
        'participation_jump': first['jump'],
        'participation_jump_threshold': min_participation_jump,
        'weak_participation_jump': first['jump'] < min_participation_jump,
        'first_stage_F': None if math.isinf(first_stage_F) else first_stage_F,
        'perfect_compliance': bool(perfect_compliance),
        'weak_first_stage': (first_stage_F is not None and first_stage_F < 10),
        'crossers': int(((z == 0) & (p == 1)).sum() + ((z == 1) & (p == 0)).sum()),
        'below_cutoff_participants': int(((z == 0) & (p == 1)).sum()),
        'above_cutoff_nonparticipants': int(((z == 1) & (p == 0)).sum()),
    }
    refusals = []
    if discrete_reasons: refusals.append('入学分离散：' + '；'.join(discrete_reasons))
    if first['jump'] < min_participation_jump:
        refusals.append(f'参辅率在门槛处的跳变仅 {first["jump"]:.2f}，低于最低要求 {min_participation_jump:.2f}')
    if first_stage_F is not None and first_stage_F < 10:
        refusals.append(f'第一阶段弱工具：F={first_stage_F:.1f} < 10')
    if perfect_compliance:
        checks['sharp_design'] = True

    participation_left = float(p[left].mean())
    participation_right = float(p[right].mean())
    if eligible_mismatch:
        refusals.append(f'{eligible_mismatch} 条样本的资格标记与门槛规则不一致，资格名册不可信')

    snapshot = [{
        'code': r['code'],
        'enrollment_score': float(r['enrollment_score']),
        'u': float(r['u']),
        'eligible': bool(z[i]),
        'participated': bool(p[i]),
        'final_score': float(y[i]),
    } for i, r in enumerate(window)]

    result = {
        'method': '模糊断点（局部线性 2SLS，三角核）；断点=入学分门槛；处理=实际参辅；结局=结课成绩',
        'estimand': '断点处合规者的实际参辅局部平均效应（LATE）',
        'threshold': threshold,
        'direction': direction,
        'bandwidth': bandwidth,
        'window_n': n,
        'left_n': int(left.sum()),
        'right_n': int(right.sum()),
        'participation_left': participation_left,
        'participation_right': participation_right,
        'first_stage_jump': first['jump'],
        'first_stage_se': first['se'],
        'first_stage_ci': [first['ci_low'], first['ci_high']],
        'first_stage_F': None if math.isinf(first_stage_F) else first_stage_F,
        'reduced_form_jump': reduced['jump'],
        'reduced_form_se': reduced['se'],
        'reduced_form_ci': [reduced['ci_low'], reduced['ci_high']],
        'late': tau,
        'late_se': se,
        'late_ci': [ci_low, ci_high],
        'p_value': p_value,
        'significant': (p_value is not None and p_value < .05),
        'eligible_n': int(z.sum()),
        'checks': checks,
        'discreteness': {
            'left_distinct': distinct_left,
            'right_distinct': distinct_right,
            'mass_at_cutoff': mass_at_cutoff,
            'reasons': discrete_reasons,
        },
        'assumptions': IDENTIFICATION_ASSUMPTIONS,
        'refusals': refusals,
        'status': 'inconclusive' if refusals else 'completed',
        'verdict': '拒绝因果结论' if refusals else '在识别假设下可报告局部因果效应',
        'cutoff_sample': snapshot,
        'window_rule': '带宽仅由入学分分布与名册人数决定；选择时未查看结课成绩',
    }
    if refusals:
        result['reason'] = '；'.join(refusals)
    return result
