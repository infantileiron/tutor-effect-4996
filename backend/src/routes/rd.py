import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from src.config.database import get_db
from src.utils.security import current_user, editor
from src.schemas.business import RdRunInput, ConclusionInput
from src.services import rd_reports
from src.controllers.business import serialize, serialize_many
router = APIRouter()


@router.get('/rd/reports')
def listing(db=Depends(get_db), user=Depends(current_user)):
    return serialize_many(rd_reports.list_reports(db))


@router.post('/rd/reports', status_code=202)
def create(data: RdRunInput, db=Depends(get_db), user=Depends(editor)):
    return serialize(rd_reports.create_report(db, data.batch_id, user))


@router.get('/rd/reports/{id}')
def detail(id: int, db=Depends(get_db), user=Depends(current_user)):
    return serialize(rd_reports.get_report(db, id))


@router.post('/rd/reports/{id}/recompute', status_code=202)
def recompute(id: int, db=Depends(get_db), user=Depends(editor)):
    return serialize(rd_reports.recompute(db, id, user))


@router.patch('/rd/reports/{id}/conclusion')
def conclusion(id: int, data: ConclusionInput, db=Depends(get_db), user=Depends(editor)):
    return serialize(rd_reports.save_conclusion(db, id, data, user))


@router.get('/rd/reports/{id}/export')
def export(id: int, db=Depends(get_db), user=Depends(current_user)):
    report = rd_reports.get_report(db, id)
    if not report.valid:
        raise HTTPException(409, '报告因资格勘误已失效，重算后才能导出')
    if report.status not in ('completed', 'inconclusive'):
        raise HTTPException(409, '报告尚未完成')
    content = {
        'rd_report_id': report.id,
        'batch_id': report.batch_id,
        'batch_revision': report.batch_revision,
        'created_at': report.created_at,
        'computed_at': report.computed_at,
        'published': report.published,
        'conclusion': report.conclusion,
        'result': report.result,
    }
    return Response(json.dumps(content, ensure_ascii=False, indent=2), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="rd-report-{id}.json"'})
