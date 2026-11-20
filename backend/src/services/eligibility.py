"""Eligibility batches: threshold-based admission, locked roster, corrections.

Design rules
------------
* A batch moves draft -> locking -> locked.  Locking is two-phase so that a
  crash between the two commits is recoverable: the partial roster is removed,
  data returns to the original draft batch, and a retry rebuilds it once.
* The roster is unique per (batch, student) in the database.  Retries reuse the
  existing rows instead of creating a second roster.
* Corrections bump ``revision`` and invalidate every RD report of the batch,
  including reports that are being published concurrently.  Both correction
  and publication take the same PostgreSQL row lock (and an in-process lock as
  a fallback for SQLite tests), so neither can miss the other's mark.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.models.entities import (
    EligibilityBatch, EligibilityCandidate, EligibilityCorrection,
    EligibilityRosterEntry, ParticipationRecord, RdReport, Student,
)
from src.services.locks import batch_lock
from src.services.rd import is_eligible, signed_distance


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _locked_batch(db, batch_id: int) -> EligibilityBatch:
    batch = db.scalar(select(EligibilityBatch).where(EligibilityBatch.id == batch_id).with_for_update())
    if not batch:
        raise HTTPException(404, '资格批次不存在')
    return batch


def _roster_checksum(entries: list[EligibilityRosterEntry], batch: EligibilityBatch) -> str:
    payload = sorted(
        ([e.student_id, round(float(e.enrollment_score), 6), bool(e.eligible)] for e in entries),
        key=lambda row: row[0],
    )
    body = {
        'batch_id': batch.id,
        'term': batch.term,
        'threshold': batch.threshold,
        'direction': batch.direction,
        'roster': payload,
    }
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _refresh_checksum(db, batch: EligibilityBatch) -> str:
    entries = db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch.id)).all()
    batch.roster_checksum = _roster_checksum(entries, batch)
    return batch.roster_checksum


# ---------------------------------------------------------------- reading

def list_batches(db):
    return db.scalars(select(EligibilityBatch).order_by(EligibilityBatch.id.desc())).all()


def get_batch(db, batch_id: int) -> EligibilityBatch:
    batch = db.get(EligibilityBatch, batch_id)
    if not batch:
        raise HTTPException(404, '资格批次不存在')
    return batch


def batch_summary(db, batch: EligibilityBatch) -> dict:
    candidates = db.scalar(select(func.count()).select_from(EligibilityCandidate).where(EligibilityCandidate.batch_id == batch.id)) or 0
    roster = db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch.id)).all()
    report_count = db.scalar(select(func.count()).select_from(RdReport).where(RdReport.batch_id == batch.id)) or 0
    latest = db.scalar(select(RdReport).where(RdReport.batch_id == batch.id).order_by(RdReport.id.desc()))
    return {
        'id': batch.id,
        'title': batch.title,
        'term': batch.term,
        'threshold': batch.threshold,
        'direction': batch.direction,
        'bandwidth': batch.bandwidth,
        'bandwidth_rule': batch.bandwidth_rule,
        'min_side_n': batch.min_side_n,
        'min_side_distinct': batch.min_side_distinct,
        'min_participation_jump': batch.min_participation_jump,
        'status': batch.status,
        'revision': batch.revision,
        'roster_checksum': batch.roster_checksum,
        'locked_at': batch.locked_at,
        'updated_at': batch.updated_at,
        'candidate_count': candidates,
        'roster_count': len(roster),
        'report_count': report_count,
        'latest_report_id': latest.id if latest else None,
        'latest_report_status': latest.status if latest else None,
        'latest_report_valid': latest.valid if latest else None,
    }


def serialize_batch(db, batch: EligibilityBatch) -> dict:
    candidates = db.execute(
        select(EligibilityCandidate, Student)
        .join(Student, Student.id == EligibilityCandidate.student_id)
        .where(EligibilityCandidate.batch_id == batch.id)
        .order_by(Student.code)
    ).all()
    roster = db.execute(
        select(EligibilityRosterEntry, Student)
        .join(Student, Student.id == EligibilityRosterEntry.student_id)
        .where(EligibilityRosterEntry.batch_id == batch.id)
        .order_by(EligibilityRosterEntry.enrollment_score, Student.code)
    ).all()
    participation = {
        p.student_id: p
        for p in db.scalars(select(ParticipationRecord).where(ParticipationRecord.batch_id == batch.id))
    }
    corrections = db.scalars(
        select(EligibilityCorrection).where(EligibilityCorrection.batch_id == batch.id).order_by(EligibilityCorrection.id)
    ).all()
    reports = db.scalars(
        select(RdReport).where(RdReport.batch_id == batch.id).order_by(RdReport.id.desc())
    ).all()
    base = batch_summary(db, batch)

    candidate_rows = [{
        'student_id': c.student_id,
        'code': s.code,
        'name': s.name,
        'campus': s.campus,
        'enrollment_score': c.enrollment_score,
        'eligible': is_eligible(c.enrollment_score, batch.threshold, batch.direction),
        'side': 'right' if signed_distance(c.enrollment_score, batch.threshold, batch.direction) >= 0 else 'left',
    } for c, s in candidates]

    roster_rows = []
    for e, s in roster:
        p = participation.get(e.student_id)
        side = 'right' if signed_distance(e.enrollment_score, batch.threshold, batch.direction) >= 0 else 'left'
        roster_rows.append({
            'student_id': e.student_id,
            'code': s.code,
            'name': s.name,
            'campus': s.campus,
            'enrollment_score': e.enrollment_score,
            'eligible': bool(e.eligible),
            'side': side,
            'distance': signed_distance(e.enrollment_score, batch.threshold, batch.direction),
            'participated': bool(p.participated) if p else False,
            'participation_note': p.note if p else '',
            'participation_updated_by': p.updated_by if p else '',
            'participation_updated_at': p.updated_at if p else None,
            'final_score': s.score,
            'absent': s.absent,
        })

    left = [r for r in roster_rows if r['side'] == 'left']
    right = [r for r in roster_rows if r['side'] == 'right']
    basis = {
        'term': batch.term,
        'threshold': batch.threshold,
        'direction': batch.direction,
        'rule': ('入学分 ≥ 门槛' if batch.direction == 'gte' else '入学分 ≤ 门槛') + ' 获得辅导资格',
        'candidate_count': base['candidate_count'],
        'roster_count': base['roster_count'],
        'eligible_count': sum(1 for r in roster_rows if r['eligible']),
        'left_count': len(left),
        'right_count': len(right),
        'bandwidth_rule': batch.bandwidth_rule,
        'bandwidth': batch.bandwidth,
        'min_side_n': batch.min_side_n,
        'min_side_distinct': batch.min_side_distinct,
        'min_participation_jump': batch.min_participation_jump,
        'roster_checksum': batch.roster_checksum,
        'revision': batch.revision,
        'locked_at': batch.locked_at,
        'note': '资格由入学分门槛决定；实际参辅单独登记，不改变资格名册。',
    }
    return {
        **base,
        'description': batch.description,
        'created_at': batch.created_at,
        'basis': basis,
        'candidates': candidate_rows,
        'roster': roster_rows,
        'corrections': [{
            'id': c.id,
            'student_id': c.student_id,
            'field': c.field,
            'old_value': c.old_value,
            'new_value': c.new_value,
            'note': c.note,
            'actor': c.actor,
            'resulting_revision': c.resulting_revision,
            'created_at': c.created_at,
        } for c in corrections],
        'reports': [{
            'id': r.id,
            'status': r.status,
            'batch_revision': r.batch_revision,
            'valid': bool(r.valid),
            'published': bool(r.published),
            'invalidated_reason': r.invalidated_reason,
            'created_at': r.created_at,
            'computed_at': r.computed_at,
        } for r in reports],
    }


# ---------------------------------------------------------------- writing

def create_batch(db, data, user) -> EligibilityBatch:
    duplicate = db.scalar(select(EligibilityBatch).where(EligibilityBatch.title == data.title))
    if duplicate:
        raise HTTPException(409, '批次名称已存在，请修改后重试')
    batch = EligibilityBatch(
        title=data.title, term=data.term, threshold=data.threshold,
        direction=data.direction, bandwidth=data.bandwidth,
        bandwidth_rule=data.bandwidth_rule, min_side_n=data.min_side_n,
        min_side_distinct=data.min_side_distinct,
        min_participation_jump=data.min_participation_jump,
        description=data.description, status='draft', revision=0,
        created_at=now(), updated_at=now(),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def update_batch(db, batch_id: int, data, user) -> EligibilityBatch:
    with batch_lock(batch_id):
        batch = _locked_batch(db, batch_id)
        if batch.status != 'draft':
            raise HTTPException(409, '批次已进入锁定流程，资格门槛不能再直接修改；请使用勘误登记')
        for key, value in data.model_dump().items():
            setattr(batch, key, value)
        batch.updated_at = now()
        db.commit()
        db.refresh(batch)
        return batch


def _resolve_student(db, data) -> Student:
    if getattr(data, 'student_id', None):
        student = db.get(Student, data.student_id)
        if not student:
            raise HTTPException(404, '学员不存在')
        return student
    code = getattr(data, 'code', None)
    if not code:
        raise HTTPException(422, '请提供已有学员编号或新学员学号')
    student = db.scalar(select(Student).where(Student.code == code))
    if student:
        return student
    student = Student(
        code=code,
        name=getattr(data, 'name', None) or code,
        campus=getattr(data, 'campus', None) or '城东',
        group='control', score=None, absent=False,
    )
    db.add(student)
    db.flush()
    return student


def upsert_candidate(db, batch_id: int, data, user) -> dict:
    with batch_lock(batch_id):
        batch = _locked_batch(db, batch_id)
        if batch.status != 'draft':
            raise HTTPException(409, '资格名册已锁定；修改入学分请走勘误登记')
        student = _resolve_student(db, data)
        if getattr(data, 'name', None):
            student.name = data.name
        if getattr(data, 'campus', None):
            student.campus = data.campus
        entry = db.scalar(select(EligibilityCandidate).where(
            EligibilityCandidate.batch_id == batch.id,
            EligibilityCandidate.student_id == student.id,
        ))
        if not entry:
            entry = EligibilityCandidate(batch_id=batch.id, student_id=student.id, created_at=now())
            db.add(entry)
        entry.enrollment_score = data.enrollment_score
        entry.updated_at = now()
        batch.updated_at = now()
        db.commit()
        return {
            'student_id': student.id, 'code': student.code, 'name': student.name,
            'campus': student.campus, 'enrollment_score': entry.enrollment_score,
        }


def remove_candidate(db, batch_id: int, student_id: int, user):
    with batch_lock(batch_id):
        batch = _locked_batch(db, batch_id)
        if batch.status != 'draft':
            raise HTTPException(409, '资格名册已锁定，不能删除候选人')
        entry = db.scalar(select(EligibilityCandidate).where(
            EligibilityCandidate.batch_id == batch.id,
            EligibilityCandidate.student_id == student_id,
        ))
        if not entry:
            raise HTTPException(404, '候选人不存在')
        db.delete(entry)
        batch.updated_at = now()
        db.commit()


def _build_roster(db, batch: EligibilityBatch) -> None:
    candidates = db.scalars(
        select(EligibilityCandidate).where(EligibilityCandidate.batch_id == batch.id)
    ).all()
    existing = {
        e.student_id: e for e in db.scalars(
            select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch.id)
        )
    }
    for candidate in candidates:
        entry = existing.get(candidate.student_id)
        if entry is None:
            db.add(EligibilityRosterEntry(
                batch_id=batch.id, student_id=candidate.student_id,
                enrollment_score=candidate.enrollment_score,
                eligible=is_eligible(candidate.enrollment_score, batch.threshold, batch.direction),
                created_at=now(),
            ))
        else:
            entry.enrollment_score = candidate.enrollment_score
            entry.eligible = is_eligible(candidate.enrollment_score, batch.threshold, batch.direction)
    db.flush()


def lock_batch(db, batch_id: int, token: str | None = None, user=None) -> dict:
    """Idempotently lock a batch and materialise the eligibility roster."""
    token = token or secrets.token_hex(16)
    with batch_lock(batch_id):
        batch = _locked_batch(db, batch_id)
        resumed = False
        if batch.status == 'locked':
            count = db.scalar(select(func.count()).select_from(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch.id)) or 0
            if count == 0:
                raise HTTPException(409, '批次已锁定但名册缺失，请先恢复为草稿再重新锁定')
            return {'batch_id': batch.id, 'status': 'locked', 'reused': True,
                    'roster_count': count, 'roster_checksum': batch.roster_checksum,
                    'revision': batch.revision, 'token': token}
        if batch.status == 'locking':
            if batch.lock_token and batch.lock_token == token:
                resumed = True
            else:
                # Previous lock was interrupted. Restore the original batch,
                # discarding any partial roster, then start a clean retry.
                _restore_draft(db, batch)
                db.commit()
        if batch.status == 'draft':
            left, right = 0, 0
            for candidate in db.scalars(select(EligibilityCandidate).where(EligibilityCandidate.batch_id == batch.id)):
                if signed_distance(candidate.enrollment_score, batch.threshold, batch.direction) >= 0:
                    right += 1
                else:
                    left += 1
            if left < 2 or right < 2:
                raise HTTPException(409, f'门槛两侧各需至少 2 名候选人（当前左 {left} / 右 {right}），无法形成资格名册')
            batch.status = 'locking'
            batch.lock_token = token
            batch.lock_started_at = now()
            batch.updated_at = now()
            db.commit()
        try:
            _build_roster(db, batch)
            batch.status = 'locked'
            batch.locked_at = now()
            batch.updated_at = now()
            batch.lock_token = None
            batch.lock_started_at = None
            _refresh_checksum(db, batch)
            db.commit()
        except Exception:
            db.rollback()
            # Restore the original batch; candidates are untouched.
            _restore_draft(db, _locked_batch(db, batch.id))
            db.commit()
            raise
        count = db.scalar(select(func.count()).select_from(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch.id)) or 0
        return {'batch_id': batch.id, 'status': 'locked', 'reused': False, 'resumed': resumed,
                'roster_count': count, 'roster_checksum': batch.roster_checksum,
                'revision': batch.revision, 'token': token}


def _restore_draft(db, batch: EligibilityBatch) -> None:
    db.execute(EligibilityRosterEntry.__table__.delete().where(EligibilityRosterEntry.batch_id == batch.id))
    batch.status = 'draft'
    batch.lock_token = None
    batch.lock_started_at = None
    batch.locked_at = None
    batch.roster_checksum = ''
    batch.updated_at = now()


def recover_batch(db, batch_id: int, user=None) -> dict:
    with batch_lock(batch_id):
        batch = _locked_batch(db, batch_id)
        if batch.status != 'locking':
            raise HTTPException(409, '只有锁定中断（locking）的批次可以恢复为草稿')
        _restore_draft(db, batch)
        db.commit()
        return {'batch_id': batch.id, 'status': batch.status, 'restored': True}


def record_participation(db, batch_id: int, data, user) -> dict:
    """Record actual participation separately from eligibility."""
    with batch_lock(batch_id):
        batch = _locked_batch(db, batch_id)
        if batch.status != 'locked':
            raise HTTPException(409, '请先锁定资格名册，再登记实际参辅')
        entry = db.scalar(select(EligibilityRosterEntry).where(
            EligibilityRosterEntry.batch_id == batch.id,
            EligibilityRosterEntry.student_id == data.student_id,
        ))
        if not entry:
            raise HTTPException(404, '该学员不在本批资格名册中')
        record = db.scalar(select(ParticipationRecord).where(
            ParticipationRecord.batch_id == batch.id,
            ParticipationRecord.student_id == data.student_id,
        ))
        old = record.participated if record else None
        old_note = record.note if record else ''
        if not record:
            record = ParticipationRecord(batch_id=batch.id, student_id=data.student_id)
            db.add(record)
        record.participated = data.participated
        record.note = data.note
        record.updated_by = getattr(user, 'email', 'seed')
        record.updated_at = now()
        changed = old is None or old != data.participated or old_note != data.note
        invalidated = 0
        if changed:
            invalidated = _invalidate_reports(db, batch, f'实际参辅登记变更（学员 {data.student_id}）')
        batch.updated_at = now()
        db.commit()
        return {'batch_id': batch.id, 'student_id': data.student_id,
                'participated': record.participated, 'invalidated_reports': invalidated}


def add_correction(db, batch_id: int, data, user) -> dict:
    """Apply an eligibility correction, bump revision, and invalidate results."""
    field = data.field
    with batch_lock(batch_id):
        batch = _locked_batch(db, batch_id)
        if batch.status != 'locked':
            raise HTTPException(409, '请先完成资格名册锁定，再进行勘误')
        student_id = data.student_id
        old_value = None
        if field in ('enrollment_score', 'participation'):
            if not student_id:
                raise HTTPException(422, '该字段勘误需要指定学员')
            entry = db.scalar(select(EligibilityRosterEntry).where(
                EligibilityRosterEntry.batch_id == batch.id,
                EligibilityRosterEntry.student_id == student_id,
            ))
            if not entry:
                raise HTTPException(404, '该学员不在本批资格名册中')
        if field == 'enrollment_score':
            try:
                new_score = float(data.new_value)
            except (TypeError, ValueError):
                raise HTTPException(422, '入学分必须是 0–100 的数字')
            if not (0 <= new_score <= 100):
                raise HTTPException(422, '入学分必须是 0–100 的数字')
            old_value = entry.enrollment_score
            entry.enrollment_score = new_score
            entry.eligible = is_eligible(new_score, batch.threshold, batch.direction)
            candidate = db.scalar(select(EligibilityCandidate).where(
                EligibilityCandidate.batch_id == batch.id,
                EligibilityCandidate.student_id == student_id,
            ))
            if candidate:
                candidate.enrollment_score = new_score
                candidate.updated_at = now()
            new_value = new_score
        elif field == 'threshold':
            try:
                new_threshold = float(data.new_value)
            except (TypeError, ValueError):
                raise HTTPException(422, '门槛必须是 0–100 的数字')
            if not (0 <= new_threshold <= 100):
                raise HTTPException(422, '门槛必须是 0–100 的数字')
            old_value = batch.threshold
            batch.threshold = new_threshold
            new_value = new_threshold
            for roster_entry in db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch.id)):
                roster_entry.eligible = is_eligible(roster_entry.enrollment_score, new_threshold, batch.direction)
        elif field == 'direction':
            new_direction = str(data.new_value)
            if new_direction not in ('gte', 'lte'):
                raise HTTPException(422, '方向只能是 gte 或 lte')
            old_value = batch.direction
            batch.direction = new_direction
            new_value = new_direction
            for roster_entry in db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch.id)):
                roster_entry.eligible = is_eligible(roster_entry.enrollment_score, batch.threshold, new_direction)
        elif field == 'participation':
            new_bool = data.new_value
            if isinstance(new_bool, str):
                new_bool = new_bool.strip().lower() in ('1', 'true', 'yes', '是')
            if not isinstance(new_bool, bool):
                raise HTTPException(422, '参辅状态必须是布尔值')
            record = db.scalar(select(ParticipationRecord).where(
                ParticipationRecord.batch_id == batch.id,
                ParticipationRecord.student_id == student_id,
            ))
            old_value = record.participated if record else None
            if not record:
                record = ParticipationRecord(batch_id=batch.id, student_id=student_id)
                db.add(record)
            record.participated = new_bool
            record.note = data.note or record.note
            record.updated_by = getattr(user, 'email', 'seed')
            record.updated_at = now()
            new_value = new_bool
        else:
            raise HTTPException(422, '不支持的勘误字段')

        batch.revision += 1
        batch.updated_at = now()
        _refresh_checksum(db, batch)
        invalidated = _invalidate_reports(
            db, batch,
            f'资格勘误 r{batch.revision}：{field} {_text(old_value)} → {_text(new_value)}',
        )
        correction = EligibilityCorrection(
            batch_id=batch.id, student_id=student_id, field=field,
            old_value=_text(old_value), new_value=_text(new_value),
            note=data.note, actor=getattr(user, 'email', 'seed'),
            resulting_revision=batch.revision, created_at=now(),
        )
        db.add(correction)
        db.commit()
        db.refresh(correction)
        return {
            'batch_id': batch.id, 'revision': batch.revision,
            'field': field, 'old_value': _text(old_value), 'new_value': _text(new_value),
            'roster_checksum': batch.roster_checksum,
            'invalidated_reports': invalidated,
            'correction_id': correction.id,
        }


def _invalidate_reports(db, batch: EligibilityBatch, reason: str) -> int:
    reports = db.scalars(select(RdReport).where(RdReport.batch_id == batch.id)).all()
    count = 0
    for report in reports:
        if report.status == 'invalid' and not report.valid:
            continue
        report.valid = False
        report.status = 'invalid'
        report.published = False
        report.invalidated_reason = reason
        report.invalidated_at = now()
        count += 1
    return count
