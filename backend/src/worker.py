import time,traceback
from pathlib import Path
from sqlalchemy import select
from src.config.database import SessionLocal
from src.models.entities import Report,Plan,Student,RdReport
from src.services.reports import queue
from src.services.statistics import welch
from src.services.rd_reports import run_queued
print('tutor effect worker started',flush=True)
while True:
    Path('/tmp/worker-heartbeat').touch()
    try:
        queue.brpop('tutor:reports',timeout=2)
        with SessionLocal() as db:
            task=db.scalar(select(Report).where(Report.status=='queued').order_by(Report.id).with_for_update(skip_locked=True))
            if not task: continue
            task.status='running';db.commit()
            try:
                plan=db.get(Plan,task.plan_id)
                task.result=welch(db.scalars(select(Student).order_by(Student.code)).all(),plan)
                task.status='completed'
            except Exception as e:
                task.error=str(e);task.status='failed'
            db.commit()
            print(f'report={task.id} status={task.status}',flush=True)
    except Exception:
        traceback.print_exc();time.sleep(2)
    try:
        queue.brpop('tutor:rd_reports',timeout=2)
        with SessionLocal() as db:
            task=db.scalar(select(RdReport).where(RdReport.status=='queued').order_by(RdReport.id).with_for_update(skip_locked=True))
            if not task: continue
            task.status='running';db.commit()
            try:
                run_queued(db,task)
            except Exception as e:
                db.rollback()
                task=db.get(RdReport,task.id)
                if task:
                    task.status='failed';task.error=str(e);db.commit()
            print(f'rd_report={task.id} status={task.status}',flush=True)
    except Exception:
        traceback.print_exc();time.sleep(2)
