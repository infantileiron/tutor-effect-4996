import math

import pytest
from sqlalchemy import select

from src.config import database
from src.models.entities import EligibilityBatch, EligibilityRosterEntry


def login(client, email='analyst@demo.local'):
    response = client.post('/auth/login', json={'email': email, 'password': 'Demo123!'})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def make_batch(client, headers, title='2026 秋季资格批次'):
    payload = {'title': title, 'term': '2026秋', 'threshold': 60, 'direction': 'gte',
               'bandwidth_rule': 'auto_min_side_n', 'min_side_n': 20, 'min_side_distinct': 10,
               'min_participation_jump': 0.2}
    response = client.post('/eligibility/batches', json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def add_candidates(client, headers, batch_id):
    students = client.get('/students', headers=headers).json()
    with database.SessionLocal() as db:
        from src.models.entities import Student
        rows = db.scalars(select(Student).order_by(Student.code)).all()
        entries = [{'student_id': s.id, 'enrollment_score': 30 + 50 * (i / 239)} for i, s in enumerate(rows)]
    for entry in entries:
        response = client.post(f'/eligibility/batches/{batch_id}/candidates', json=entry, headers=headers)
        assert response.status_code == 201, response.text


def lock(client, headers, batch_id):
    response = client.post(f'/eligibility/batches/{batch_id}/lock', headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def record_participation(client, headers, batch_id):
    detail = client.get(f'/eligibility/batches/{batch_id}', headers=headers).json()
    for row in detail['roster']:
        idx = int(row['code'][1:])
        eligible = row['side'] == 'right'
        participated = (idx % 10 != 0) if eligible else (idx % 5 == 0)
        response = client.post(f'/eligibility/batches/{batch_id}/participation',
                               json={'student_id': row['student_id'], 'participated': participated}, headers=headers)
        assert response.status_code == 200, response.text


def run_and_wait(client, headers, batch_id):
    response = client.post('/rd/reports', json={'batch_id': batch_id}, headers=headers)
    assert response.status_code == 202, response.text
    report_id = response.json()['id']
    # process synchronously the way the worker does
    from src.config.database import SessionLocal
    from src.models.entities import RdReport
    from src.services.rd_reports import run_queued
    with SessionLocal() as db:
        run_queued(db, db.get(RdReport, report_id))
    detail = client.get(f'/rd/reports/{report_id}', headers=headers).json()
    return detail


def test_locked_roster_and_fuzzy_late(client):
    headers = login(client)
    batch = make_batch(client, headers)
    add_candidates(client, headers, batch['id'])
    locked = lock(client, headers, batch['id'])
    assert locked['status'] == 'locked'
    assert locked['roster_count'] == 240
    assert len(locked['roster_checksum']) == 64
    record_participation(client, headers, batch['id'])
    report = run_and_wait(client, headers, batch['id'])
    assert report['status'] == 'completed', report
    result = report['result']
    assert result['status'] == 'completed'
    assert result['assumptions']
    assert result['late_ci'][0] < result['late'] < result['late_ci'][1]
    assert abs(result['late'] - 6) < 6
    assert result['window_rule']


def test_correction_invalidates_results_and_recompute_restores(client):
    headers = login(client)
    batch = make_batch(client, headers)
    add_candidates(client, headers, batch['id'])
    lock(client, headers, batch['id'])
    record_participation(client, headers, batch['id'])
    report = run_and_wait(client, headers, batch['id'])
    admin = login(client, 'admin@demo.local')
    published = client.patch(f"/rd/reports/{report['id']}/conclusion",
                             json={'conclusion': '断点处参辅约有 6 分局部效应。', 'published': True}, headers=admin)
    assert published.status_code == 200, published.text
    correction = client.post(f"/eligibility/batches/{batch['id']}/corrections",
                             json={'field': 'threshold', 'new_value': 61, 'note': '勘误门槛'}, headers=headers)
    assert correction.status_code == 201, correction.text
    stale = client.get(f"/rd/reports/{report['id']}", headers=headers).json()
    assert stale['valid'] is False
    assert stale['status'] == 'invalid'
    assert stale['published'] is False
    blocked = client.patch(f"/rd/reports/{report['id']}/conclusion",
                           json={'conclusion': '试图发布失效结果。', 'published': True}, headers=admin)
    assert blocked.status_code == 409
    again = run_and_wait(client, headers, batch['id'])
    assert again['valid'] is True
    assert again['batch_revision'] == correction.json()['revision']


def test_retry_lock_is_idempotent(client):
    headers = login(client)
    batch = make_batch(client, headers)
    add_candidates(client, headers, batch['id'])
    first = lock(client, headers, batch['id'])
    second = lock(client, headers, batch['id'])
    assert first['roster_count'] == second['roster_count']
    assert second['reused'] is True
    with database.SessionLocal() as db:
        count = len(db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch['id'])).all())
    assert count == 240


def test_interrupted_lock_recovers_original_batch(client):
    headers = login(client)
    batch = make_batch(client, headers)
    add_candidates(client, headers, batch['id'])
    with database.SessionLocal() as db:
        row = db.get(EligibilityBatch, batch['id'])
        row.status = 'locking'
        row.lock_token = 'crashed-token'
        db.commit()
    recovered = client.post(f"/eligibility/batches/{batch['id']}/recover", headers=headers)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()['status'] == 'draft'
    locked = lock(client, headers, batch['id'])
    assert locked['roster_count'] == 240


def test_weak_jump_refuses_causal_claim(client):
    headers = login(client)
    batch = make_batch(client, headers)
    add_candidates(client, headers, batch['id'])
    lock(client, headers, batch['id'])
    detail = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
    for row in detail['roster']:
        response = client.post(f"/eligibility/batches/{batch['id']}/participation",
                               json={'student_id': row['student_id'], 'participated': True}, headers=headers)
        assert response.status_code == 200
    report = run_and_wait(client, headers, batch['id'])
    assert report['status'] == 'inconclusive'
    assert report['result']['refusals']


def test_discrete_scores_refuse_causal_claim(client):
    headers = login(client)
    batch = make_batch(client, headers)
    students = client.get('/students', headers=headers).json()
    with database.SessionLocal() as db:
        from src.models.entities import Student
        rows = db.scalars(select(Student).order_by(Student.code)).all()
    for i, s in enumerate(rows):
        score = 55.0 if i < 120 else 65.0
        client.put(f"/eligibility/batches/{batch['id']}/candidates/{s.id}",
                   json={'enrollment_score': score}, headers=headers)
    locked = lock(client, headers, batch['id'])
    assert locked['status'] == 'locked'
    detail = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
    for row in detail['roster']:
        client.post(f"/eligibility/batches/{batch['id']}/participation",
                    json={'student_id': row['student_id'], 'participated': row['side'] == 'right'}, headers=headers)
    report = run_and_wait(client, headers, batch['id'])
    assert report['status'] == 'inconclusive'
    joined = report['result']['reason'] + str(report['result'].get('discreteness', {}))
    assert '入学分离散' in report['result']['reason'] or '离散' in joined


def test_interrupted_lock_with_partial_roster_retry_does_not_duplicate(client):
    headers = login(client)
    batch = make_batch(client, headers, title='中断重试批次')
    add_candidates(client, headers, batch['id'])
    with database.SessionLocal() as db:
        row = db.get(EligibilityBatch, batch['id'])
        row.status = 'locking'
        row.lock_token = 'crashed-token'
        db.commit()
        detail = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
        candidates = db.scalars(select(__import__('src.models.entities', fromlist=['EligibilityCandidate']).EligibilityCandidate)
                                .where(__import__('src.models.entities', fromlist=['EligibilityCandidate']).EligibilityCandidate.batch_id == batch['id'])).all()
        # simulate a half-written roster from the crashed attempt
        from src.models.entities import EligibilityRosterEntry
        for c in candidates[:37]:
            db.add(EligibilityRosterEntry(batch_id=batch['id'], student_id=c.student_id,
                                          enrollment_score=c.enrollment_score, eligible=True))
        db.commit()
        assert len(db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch['id'])).all()) == 37

    # Retrying the lock without a matching token restores the draft first.
    retried = lock(client, headers, batch['id'])
    assert retried['roster_count'] == 240
    assert retried['resumed'] is False
    with database.SessionLocal() as db:
        from src.models.entities import EligibilityRosterEntry
        rows = db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch['id'])).all()
        assert len(rows) == 240
        assert len({r.student_id for r in rows}) == 240

    # A second retry must reuse the locked roster.
    again = lock(client, headers, batch['id'])
    assert again['reused'] is True
    with database.SessionLocal() as db:
        from src.models.entities import EligibilityRosterEntry
        assert len(db.scalars(select(EligibilityRosterEntry).where(EligibilityRosterEntry.batch_id == batch['id'])).all()) == 240


def test_perfect_compliance_is_not_refused_solely_for_no_crossers(client):
    headers = login(client)
    batch = make_batch(client, headers, title='完全合规批次')
    add_candidates(client, headers, batch['id'])
    lock(client, headers, batch['id'])
    detail = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
    for row in detail['roster']:
        client.post(f"/eligibility/batches/{batch['id']}/participation",
                    json={'student_id': row['student_id'], 'participated': row['side'] == 'right'}, headers=headers)
    report = run_and_wait(client, headers, batch['id'])
    result = report['result']
    assert result['checks']['perfect_compliance'] is True
    assert result['checks']['sharp_design'] is True
    assert not any('无越线参辅' in reason for reason in result.get('refusals', []))
    assert report['status'] == 'completed', result.get('refusals')
