"""RD result lifecycle: queue, compute, publish, invalidate, recompute.

Locking order is always batch row -> report row.  Corrections lock the batch
row, so a publication racing with a correction is serialized: the publisher
sees the bumped revision and refuses to publish a stale result, and the
correction marks every report (including a just-published one) invalid.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import redis
from fastapi import HTTPException
from sqlalchemy import select

from src.models.entities import (
    EligibilityBatch, EligibilityRosterEntry, ParticipationRecord, RdReport, Student,
)
from src.services.locks import batch_lock
from src.services.rd import choose_bandwidth, fuzzy_local_rd

queue = redis.Redis.from_url(os.environ['REDIS_URL'])
MAX_PENDING = 10


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_reports(db):
    return db.scalars(select(RdReport).order_by(RdReport.id.desc())).all()


def get_report(db, report_id: int) -> RdReport:
    report = db.get(RdReport, report_id)
    if not report:
        raise HTTPException(404, '断点检验报告不存在')
    return report


def _batch_locked(db, batch_id: int) -> EligibilityBatch:
    batch = db.scalar(select(EligibilityBatch).where(EligibilityBatch.id == batch_id).with_for_update())
    if not batch:
        raise HTTPException(404, '资格批次不存在')
    return batch


def create_report(db, batch_id: int, user):
    with batch_lock(batch_id):
        batch = _batch_locked(db, batch_id)
        if batch.status != 'locked':
            raise HTTPException(409, '资格名册锁定后才能提交断点检验')
        pending = db.scalars(select(RdReport).where(RdReport.status.in_(['queued', 'running']))).all()
        if len(pending) >= MAX_PENDING:
            raise HTTPException(429, '待执行任务已达10个，请稍后再试')
        report = RdReport(batch_id=batch.id, status='queued', batch_revision=batch.revision,
                          valid=True, created_at=now())
        db.add(report)
        db.commit()
        db.refresh(report)
        _notify(report.id)
        return report


def _notify(report_id: int) -> None:
    """Wake the worker; a lost notification is recovered by the DB scan."""
    try:
        queue.lpush('tutor:rd_reports', report_id)
    except Exception:  # noqa: BLE001 - the worker also scans queued rows
        pass


def _load_rows(db, batch: EligibilityBatch) -> list[dict]:
    entries = db.execute(
        select(EligibilityRosterEntry, Student)
        .join(Student, Student.id == EligibilityRosterEntry.student_id)
        .where(EligibilityRosterEntry.batch_id == batch.id)
    ).all()
    participation = {
        p.student_id: p.participated
        for p in db.scalars(select(ParticipationRecord).where(ParticipationRecord.batch_id == batch.id))
    }
    rows = []
    for entry, student in entries:
        if student.score is None or student.absent:
            continue
        rows.append({
            'code': student.code,
            'enrollment_score': float(entry.enrollment_score),
            'participated': bool(participation.get(student.id, False)),
            'outcome': float(student.score),
            'eligible': bool(entry.eligible),
        })
    return rows


def compute(db, report: RdReport) -> dict:
    """Run the estimator from a locked roster and persist the result."""
    batch = db.get(EligibilityBatch, report.batch_id)
    rows = _load_rows(db, batch)
    if not rows:
        raise ValueError('资格名册内没有可用的结课成绩；请先补齐成绩或检查缺考标记')
    scores = [r['enrollment_score'] for r in rows]
    bandwidth = batch.bandwidth
    basis = {}
    if batch.bandwidth_rule == 'manual':
        chosen = choose_bandwidth(scores, batch.threshold, batch.direction, rule='manual',
                                  manual=bandwidth, min_side_n=batch.min_side_n,
                                  min_side_distinct=batch.min_side_distinct)
        basis = chosen['basis']
        bandwidth = chosen['bandwidth']
        if bandwidth is None:
            from src.services.rd import IDENTIFICATION_ASSUMPTIONS
            return {
                'status': 'inconclusive',
                'reason': '手动带宽下断点两侧样本不足，拒绝给出因果结论',
                'bandwidth': batch.bandwidth,
                'bandwidth_basis': basis,
                'assumptions': IDENTIFICATION_ASSUMPTIONS,
                'refusals': ['带宽内断点两侧样本不足'],
                'verdict': '拒绝因果结论',
                'batch_revision': batch.revision,
                'roster_checksum': batch.roster_checksum,
            }
    else:
        chosen = choose_bandwidth(scores, batch.threshold, batch.direction,
                                  rule='auto_min_side_n', min_side_n=batch.min_side_n,
                                  min_side_distinct=batch.min_side_distinct)
        basis = chosen['basis']
        bandwidth = chosen['bandwidth']
        if bandwidth is None:
            from src.services.rd import IDENTIFICATION_ASSUMPTIONS, signed_distance
            widest = max((abs(signed_distance(float(s), batch.threshold, batch.direction)) for s in scores), default=0.0)
            result = fuzzy_local_rd(rows, batch.threshold, batch.direction, max(widest, 1e-6),
                                    min_participation_jump=batch.min_participation_jump,
                                    kernel='uniform')
            result['status'] = 'inconclusive'
            result['verdict'] = '拒绝因果结论'
            result['refusals'] = list(dict.fromkeys(
                ['自动带宽规则找不到满足两侧最小样本要求的窗口'] + result.get('refusals', [])
            ))
            result['reason'] = '；'.join(result['refusals'])
            result['bandwidth'] = None
            result['attempted_bandwidth'] = widest
            result['bandwidth_basis'] = basis
            result['assumptions'] = IDENTIFICATION_ASSUMPTIONS
            result['batch_revision'] = batch.revision
            result['roster_checksum'] = batch.roster_checksum
            return result
    result = fuzzy_local_rd(rows, batch.threshold, batch.direction, bandwidth,
                            min_participation_jump=batch.min_participation_jump)
    result['bandwidth_basis'] = basis
    result['batch_revision'] = batch.revision
    result['roster_checksum'] = batch.roster_checksum
    return result


def run_queued(db, report: RdReport):
    """Worker path. Re-validates the batch revision before finalising."""
    batch = db.get(EligibilityBatch, report.batch_id)
    if not batch:
        report.status = 'failed'
        report.error = '资格批次已不存在'
        db.commit()
        return
    try:
        result = compute(db, report)
    except Exception as exc:  # noqa: BLE001 - surface a readable reason
        report.error = str(exc)
        report.status = 'failed'
        db.commit()
        return
    # Finalise while holding the batch row lock, then compare revisions.
    with batch_lock(batch.id):
        locked = _batch_locked(db, batch.id)
        if locked.revision != report.batch_revision:
            report.valid = False
            report.status = 'invalid'
            report.invalidated_reason = f'计算期间资格名册修订到 r{locked.revision}，本次结果失效'
            report.invalidated_at = now()
        else:
            report.result = result
            report.status = 'inconclusive' if result.get('status') == 'inconclusive' else 'completed'
            report.computed_at = now()
            report.valid = True
            report.error = '' if report.status == 'completed' else result.get('reason', '')
        db.commit()


def save_conclusion(db, report_id: int, data, user):
    report = get_report(db, report_id)
    with batch_lock(report.batch_id):
        batch = _batch_locked(db, report.batch_id)
        report = db.scalar(select(RdReport).where(RdReport.id == report_id).with_for_update())
        if not report.valid:
            raise HTTPException(409, '该报告因资格勘误已失效，请重算后再发布')
        if report.status not in ('completed', 'inconclusive'):
            raise HTTPException(409, '检验完成后才能起草结论')
        if report.batch_revision != batch.revision:
            raise HTTPException(409, '资格名册已修订，请先重算该报告')
        if report.published and user.role != 'admin':
            raise HTTPException(403, '已签核报告仅管理员可更改')
        if data.published and user.role != 'admin':
            raise HTTPException(403, '仅管理员可签核发布')
        if data.published and report.status == 'inconclusive':
            raise HTTPException(409, '结果为“拒绝因果结论”，不能签核为有效因果结论；请补足识别条件后重算')
        report.conclusion = data.conclusion
        report.published = data.published
        db.commit()
        db.refresh(report)
        return report


def recompute(db, report_id: int, user):
    previous = get_report(db, report_id)
    if previous.status in ('queued', 'running'):
        raise HTTPException(409, '原报告仍在计算，请稍后再重算')
    with batch_lock(previous.batch_id):
        batch = _batch_locked(db, previous.batch_id)
        if batch.status != 'locked':
            raise HTTPException(409, '资格名册未锁定，不能重算')
        pending = db.scalars(select(RdReport).where(RdReport.status.in_(['queued', 'running']))).all()
        if len(pending) >= MAX_PENDING:
            raise HTTPException(429, '待执行任务已达10个，请稍后再试')
        report = RdReport(batch_id=batch.id, status='queued', batch_revision=batch.revision,
                          valid=True, recomputed_from_id=previous.id, created_at=now())
        db.add(report)
        db.commit()
        db.refresh(report)
        _notify(report.id)
        return report


def invalidate_all(db, batch_id: int, reason: str) -> int:
    from src.services.eligibility import _invalidate_reports
    batch = db.get(EligibilityBatch, batch_id)
    return _invalidate_reports(db, batch, reason)
