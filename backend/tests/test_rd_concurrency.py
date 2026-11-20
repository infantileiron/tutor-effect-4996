import threading

from sqlalchemy import select

from src.config import database
from src.models.entities import EligibilityBatch, RdReport
from src.services import eligibility, rd_reports


class DummyUser:
    def __init__(self, role='admin', email='admin@demo.local'):
        self.role = role
        self.email = email


def _prepare(client, headers):
    from tests.test_rd_eligibility import make_batch, add_candidates, lock, record_participation, run_and_wait
    batch = make_batch(client, headers, title='并发批次')
    add_candidates(client, headers, batch['id'])
    lock(client, headers, batch['id'])
    record_participation(client, headers, batch['id'])
    report = run_and_wait(client, headers, batch['id'])
    assert report['status'] == 'completed'
    return batch['id'], report['id']


def _run_concurrently(fn_a, fn_b):
    results = {}
    errors = {}

    def wrap(name, fn):
        try:
            results[name] = fn()
        except Exception as exc:  # noqa: BLE001
            errors[name] = exc

    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=wrap, args=(name, lambda fn=fn: (barrier.wait(), fn())[1]))
               for name, fn in (('a', fn_a), ('b', fn_b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def test_concurrent_correction_and_publication_never_leaves_stale_valid_report(client):
    headers = {"Authorization": "Bearer " + client.post(
        '/auth/login', json={'email': 'admin@demo.local', 'password': 'Demo123!'}).json()['access_token']}
    batch_id, report_id = _prepare(client, headers)

    class Bare:
        conclusion = '并发发布'
        published = True

    def publish():
        with database.SessionLocal() as db:
            return rd_reports.save_conclusion(db, report_id, Bare(), DummyUser())

    class Corr:
        field = 'threshold'
        new_value = 61
        student_id = None
        note = '并发勘误'

    def correct():
        with database.SessionLocal() as db:
            return eligibility.add_correction(db, batch_id, Corr(), DummyUser())

    results, errors = _run_concurrently(publish, correct)
    with database.SessionLocal() as db:
        report = db.get(RdReport, report_id)
        batch = db.get(EligibilityBatch, batch_id)
        assert batch.revision == 1
        if 'a' in results:
            # publish won the race: the correction must still mark it invalid
            assert report.valid is False
            assert report.published is False
            assert report.batch_revision != batch.revision
        else:
            # correction won: publication must be rejected, not silently stale
            assert isinstance(errors.get('a'), Exception)
            assert report.valid is False


def test_publication_after_correction_is_rejected(client):
    headers = {"Authorization": "Bearer " + client.post(
        '/auth/login', json={'email': 'admin@demo.local', 'password': 'Demo123!'}).json()['access_token']}
    batch_id, report_id = _prepare(client, headers)
    client.post(f'/eligibility/batches/{batch_id}/corrections',
                json={'field': 'threshold', 'new_value': 61}, headers=headers)

    class Bare:
        conclusion = '过期发布'
        published = True

    try:
        with database.SessionLocal() as db:
            rd_reports.save_conclusion(db, report_id, Bare(), DummyUser())
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, 'status_code', None) == 409
    else:
        raise AssertionError('stale publication should be rejected')


def test_bandwidth_is_independent_of_final_scores(client):
    headers = {"Authorization": "Bearer " + client.post(
        '/auth/login', json={'email': 'analyst@demo.local', 'password': 'Demo123!'}).json()['access_token']}
    batch_id, report_id = _prepare(client, headers)
    with database.SessionLocal() as db:
        before = db.get(RdReport, report_id).result
        from src.models.entities import Student
        students = db.scalars(select(Student).order_by(Student.code)).all()
        for i, s in enumerate(students):
            s.score = round((s.score or 0) + (10 if i % 2 else -10), 1)
        db.commit()
    # recompute with the same enrolment data but different final scores
    with database.SessionLocal() as db:
        from src.services.rd_reports import compute
        report = RdReport(batch_id=batch_id, status='queued', batch_revision=db.get(EligibilityBatch, batch_id).revision)
        db.add(report)
        db.commit()
        after = compute(db, report)
    assert before['bandwidth'] == after['bandwidth']
    assert before['window_n'] == after['window_n']
    assert before['bandwidth_basis']['left_n'] == after['bandwidth_basis']['left_n']
    assert before['late'] != after['late']
