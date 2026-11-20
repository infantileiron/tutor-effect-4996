import random,json
from datetime import datetime,timezone
from sqlalchemy import select,func
from src.config.database import Base,engine,SessionLocal
from src.models.entities import User,Student,Plan,Report,EligibilityBatch,EligibilityCandidate,EligibilityRosterEntry,ParticipationRecord
from src.utils.security import hash_password
from src.services.statistics import welch
from src.services.eligibility import lock_batch
from src.services.rd import is_eligible

SEED_TITLE='2026秋季 · 入学分60资格批次'

def seed():
    Base.metadata.create_all(engine)
    rng=random.Random(20261115)
    with SessionLocal() as db:
        for role in ('admin','analyst','viewer'):
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)): db.add(User(email=email,role=role,password_hash=hash_password('Demo123!')))
        for i in range(160):
            code=f'ZX-2026-{i+1:03}'
            group='control' if i<80 else 'intervention'
            score=round(min(100,max(0,rng.gauss(72 if group=='control' else 78,8))),1)
            absent=i%23==0
            if not db.scalar(select(Student).where(Student.code==code)):
                db.add(Student(code=code,name=f'学员{i+1:03}',campus=['城东','城西','滨江','高新'][i%4],group=group,score=None if absent else score,absent=absent))
        title='2026秋季 · 晚间小组辅导'
        plan=db.scalar(select(Plan).where(Plan.title==title))
        if not plan:
            plan=Plan(title=title,campus='全部',exclude_absent=True,description='评估每周两次小组辅导与常规自习的期末成绩差异。缺考学员排除；观察性结果不直接证明因果。');db.add(plan);db.flush()
        db.commit()
        if not db.scalar(select(Report).where(Report.plan_id==plan.id)):
            result=welch(db.scalars(select(Student).order_by(Student.code)).all(),plan)
            db.add(Report(plan_id=plan.id,status='completed',result=result,created_at=datetime.now(timezone.utc).isoformat(),conclusion='干预组均分较高。建议保留教学点分层观察，并在下一轮随机分组验证。',published=True));db.commit()
        _seed_eligibility(db,rng)
        print(json.dumps({table:db.scalar(select(func.count()).select_from(model)) for table,model in [('users',User),('students',Student),('plans',Plan),('reports',Report),('eligibility_batches',EligibilityBatch),('roster_entries',EligibilityRosterEntry),('participation',ParticipationRecord)]}))

def _seed_eligibility(db,rng):
    """A deterministic, lockable demo batch with a real participation jump.

    Enrolment scores are drawn around a 60 threshold.  Roster membership is
    deterministic in the enrolment score, while actual participation is
    recorded separately and only loosely tied to eligibility, so the demo
    contains both above-cutoff non-participants and below-cutoff participants.
    """
    batch=db.scalar(select(EligibilityBatch).where(EligibilityBatch.title==SEED_TITLE))
    if batch: return
    batch=EligibilityBatch(
        title=SEED_TITLE,term='2026秋季',threshold=60,direction='gte',
        bandwidth_rule='auto_min_side_n',bandwidth=None,
        min_side_n=20,min_side_distinct=10,min_participation_jump=.2,
        status='draft',revision=0,description='按入学分 60 分划定辅导资格，另行登记实际参辅，用于模糊断点估计。',
        created_at=datetime.now(timezone.utc).isoformat(),updated_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(batch);db.flush()
    existing={s.code:s for s in db.scalars(select(Student))}
    enrol=[];participation={}
    for i in range(120):
        code=f'RD-2026-{i+1:03}'
        score=round(min(100,max(0,rng.gauss(62,9))),1)
        while any(abs(score-e)<.05 for e in enrol): score=round(score+.1,1)
        enrol.append(score)
        participated=(i%10!=0) if score>=60 else (i%5==0)
        participation[code]=participated
        student=existing.get(code)
        if not student:
            final=round(min(100,max(0,55+.4*score+(6 if participated else 0)+rng.gauss(0,4))),1)
            student=Student(code=code,name=f'资格学员{i+1:03}',campus=['城东','城西','滨江','高新'][i%4],
                            group='control',score=final,absent=False)
            db.add(student);db.flush()
        db.add(EligibilityCandidate(batch_id=batch.id,student_id=student.id,enrollment_score=score,
                                    created_at=datetime.now(timezone.utc).isoformat(),updated_at=datetime.now(timezone.utc).isoformat()))
    db.commit()
    lock_batch(db,batch.id)
    entries=db.execute(
        select(EligibilityRosterEntry,Student).join(Student,Student.id==EligibilityRosterEntry.student_id)
        .where(EligibilityRosterEntry.batch_id==batch.id)
    ).all()
    for entry,student in entries:
        db.add(ParticipationRecord(batch_id=batch.id,student_id=entry.student_id,
                                   participated=participation.get(student.code,False),
                                   note='seed 演示数据',updated_by='seed',updated_at=datetime.now(timezone.utc).isoformat()))
    db.commit()

if __name__=='__main__': seed()
