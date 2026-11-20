"""Contract checks for the fields the frontend reads."""
from tests.test_rd_eligibility import login, make_batch, add_candidates, lock, record_participation, run_and_wait


def test_ui_contract_fields(client):
    headers = login(client)
    batch = make_batch(client, headers)
    detail = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
    for key in ('basis', 'candidates', 'roster', 'corrections', 'reports', 'status',
                'roster_checksum', 'revision', 'min_side_n', 'min_side_distinct',
                'min_participation_jump', 'bandwidth_rule'):
        assert key in detail, key
    for key in ('eligible_count', 'left_count', 'right_count', 'rule'):
        assert key in detail['basis'], key
    add_candidates(client, headers, batch['id'])
    lock(client, headers, batch['id'])
    record_participation(client, headers, batch['id'])
    detail = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
    row = detail['roster'][0]
    for key in ('student_id', 'code', 'name', 'campus', 'enrollment_score', 'eligible',
                'side', 'distance', 'participated', 'final_score'):
        assert key in row, key
    roster = client.get(f"/eligibility/batches/{batch['id']}/roster", headers=headers).json()
    assert roster['basis']['roster_checksum'] == detail['roster_checksum']

    report = run_and_wait(client, headers, batch['id'])
    for key in ('valid', 'status', 'batch_revision', 'result'):
        assert key in report, key
    result = report['result']
    for key in ('late', 'late_ci', 'first_stage_jump', 'first_stage_ci', 'reduced_form_jump',
                'bandwidth', 'window_n', 'left_n', 'right_n', 'checks', 'assumptions',
                'bandwidth_basis', 'cutoff_sample', 'window_rule'):
        assert key in result, key
    assert result['bandwidth_basis']['uses_outcome'] is False
    assert result['window_rule'].endswith('选择时未查看结课成绩')
    for key in ('above_cutoff_nonparticipants', 'below_cutoff_participants', 'perfect_compliance'):
        assert key in result['checks'], key

    export = client.get(f"/rd/reports/{report['id']}/export", headers=headers)
    assert export.status_code == 200
    body = export.json()
    assert body['result']['assumptions']
    assert body['batch_revision'] == report['batch_revision']


def test_viewer_is_read_only_for_eligibility(client):
    viewer = login(client, 'viewer@demo.local')
    analyst = login(client)
    batch = make_batch(client, analyst, title='只读检查批次')
    denied = client.post('/eligibility/batches', json={
        'title': '越权批次', 'threshold': 60}, headers=viewer)
    assert denied.status_code == 403
    assert client.get(f"/eligibility/batches/{batch['id']}", headers=viewer).status_code == 200
    assert client.post(f"/eligibility/batches/{batch['id']}/lock", headers=viewer).status_code == 403
    assert client.post(f"/eligibility/batches/{batch['id']}/corrections",
                       json={'field': 'threshold', 'new_value': 61}, headers=viewer).status_code == 403


def test_locked_batch_rejects_threshold_edit(client):
    headers = login(client)
    batch = make_batch(client, headers, title='锁定后不可改')
    add_candidates(client, headers, batch['id'])
    lock(client, headers, batch['id'])
    conflict = client.put(f"/eligibility/batches/{batch['id']}", json={
        'title': '锁定后不可改', 'term': '2026秋', 'threshold': 65, 'direction': 'gte'}, headers=headers)
    assert conflict.status_code == 409
    correction = client.post(f"/eligibility/batches/{batch['id']}/corrections",
                             json={'field': 'threshold', 'new_value': 65}, headers=headers)
    assert correction.status_code == 201
    corrected = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
    assert corrected['threshold'] == 65
    eligible = [r for r in corrected['roster'] if r['eligible']]
    assert all(r['enrollment_score'] >= 65 for r in eligible)


def test_inconclusive_report_cannot_be_published(client):
    headers = login(client)
    batch = make_batch(client, headers, title='不可发布批次')
    add_candidates(client, headers, batch['id'])
    lock(client, headers, batch['id'])
    detail = client.get(f"/eligibility/batches/{batch['id']}", headers=headers).json()
    for row in detail['roster']:
        client.post(f"/eligibility/batches/{batch['id']}/participation",
                    json={'student_id': row['student_id'], 'participated': True}, headers=headers)
    report = run_and_wait(client, headers, batch['id'])
    assert report['status'] == 'inconclusive'
    admin = login(client, 'admin@demo.local')
    blocked = client.patch(f"/rd/reports/{report['id']}/conclusion",
                           json={'conclusion': '强行签核因果结论。', 'published': True}, headers=admin)
    assert blocked.status_code == 409
    export = client.get(f"/rd/reports/{report['id']}/export", headers=headers)
    assert export.status_code == 200  # inconclusive evidence is still archivable
    client.post(f"/eligibility/batches/{batch['id']}/corrections",
                json={'field': 'threshold', 'new_value': 61}, headers=headers)
    assert client.get(f"/rd/reports/{report['id']}/export", headers=headers).status_code == 409
