from sqlalchemy import String,Float,Boolean,Integer,ForeignKey,JSON,Text,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(120),unique=True)
    role:Mapped[str]=mapped_column(String(20))
    password_hash:Mapped[str]=mapped_column(String(200))
class Student(Base):
    __tablename__='students'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    name:Mapped[str]=mapped_column(String(80))
    campus:Mapped[str]=mapped_column(String(50))
    group:Mapped[str]=mapped_column(String(20))
    score:Mapped[float|None]=mapped_column(Float,nullable=True)
    absent:Mapped[bool]=mapped_column(Boolean,default=False)
class Plan(Base):
    __tablename__='plans'
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120),unique=True)
    campus:Mapped[str]=mapped_column(String(50),default='全部')
    exclude_absent:Mapped[bool]=mapped_column(Boolean,default=True)
    description:Mapped[str]=mapped_column(Text,default='')
class Report(Base):
    __tablename__='reports'
    id:Mapped[int]=mapped_column(primary_key=True)
    plan_id:Mapped[int]=mapped_column(ForeignKey('plans.id'))
    status:Mapped[str]=mapped_column(String(20),default='queued')
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')
    conclusion:Mapped[str]=mapped_column(Text,default='')
    published:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[str]=mapped_column(String(40))
class Audit(Base):
    __tablename__='audit_logs'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(120))
    action:Mapped[str]=mapped_column(String(200))
    status:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[str]=mapped_column(String(40))

class EligibilityBatch(Base):
    __tablename__='eligibility_batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120),unique=True)
    term:Mapped[str]=mapped_column(String(80),default='')
    threshold:Mapped[float]=mapped_column(Float)
    direction:Mapped[str]=mapped_column(String(10),default='gte')
    bandwidth:Mapped[float|None]=mapped_column(Float,nullable=True)
    bandwidth_rule:Mapped[str]=mapped_column(String(60),default='auto_min_side_n')
    bandwidth_basis:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    min_side_n:Mapped[int]=mapped_column(Integer,default=5)
    min_side_distinct:Mapped[int]=mapped_column(Integer,default=5)
    min_participation_jump:Mapped[float]=mapped_column(Float,default=0.2)
    status:Mapped[str]=mapped_column(String(20),default='draft')
    revision:Mapped[int]=mapped_column(Integer,default=0)
    lock_token:Mapped[str|None]=mapped_column(String(64),nullable=True)
    lock_started_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    locked_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    roster_checksum:Mapped[str]=mapped_column(String(64),default='')
    description:Mapped[str]=mapped_column(Text,default='')
    created_at:Mapped[str]=mapped_column(String(40),default='')
    updated_at:Mapped[str]=mapped_column(String(40),default='')

class EligibilityCandidate(Base):
    __tablename__='eligibility_candidates'
    __table_args__=(UniqueConstraint('batch_id','student_id',name='uq_eligibility_candidate'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('eligibility_batches.id'))
    student_id:Mapped[int]=mapped_column(ForeignKey('students.id'))
    enrollment_score:Mapped[float]=mapped_column(Float)
    created_at:Mapped[str]=mapped_column(String(40),default='')
    updated_at:Mapped[str]=mapped_column(String(40),default='')

class EligibilityRosterEntry(Base):
    __tablename__='eligibility_roster_entries'
    __table_args__=(UniqueConstraint('batch_id','student_id',name='uq_eligibility_roster'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('eligibility_batches.id'))
    student_id:Mapped[int]=mapped_column(ForeignKey('students.id'))
    enrollment_score:Mapped[float]=mapped_column(Float)
    eligible:Mapped[bool]=mapped_column(Boolean,default=False)
    created_at:Mapped[str]=mapped_column(String(40),default='')

class ParticipationRecord(Base):
    __tablename__='participation_records'
    __table_args__=(UniqueConstraint('batch_id','student_id',name='uq_participation_record'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('eligibility_batches.id'))
    student_id:Mapped[int]=mapped_column(ForeignKey('students.id'))
    participated:Mapped[bool]=mapped_column(Boolean,default=False)
    note:Mapped[str]=mapped_column(Text,default='')
    updated_by:Mapped[str]=mapped_column(String(120),default='')
    updated_at:Mapped[str]=mapped_column(String(40),default='')

class EligibilityCorrection(Base):
    __tablename__='eligibility_corrections'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('eligibility_batches.id'))
    student_id:Mapped[int|None]=mapped_column(ForeignKey('students.id'),nullable=True)
    field:Mapped[str]=mapped_column(String(40))
    old_value:Mapped[str]=mapped_column(Text,default='')
    new_value:Mapped[str]=mapped_column(Text,default='')
    note:Mapped[str]=mapped_column(Text,default='')
    actor:Mapped[str]=mapped_column(String(120),default='')
    resulting_revision:Mapped[int]=mapped_column(Integer,default=0)
    created_at:Mapped[str]=mapped_column(String(40),default='')

class RdReport(Base):
    __tablename__='rd_reports'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('eligibility_batches.id'))
    status:Mapped[str]=mapped_column(String(20),default='queued')
    batch_revision:Mapped[int]=mapped_column(Integer,default=0)
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')
    conclusion:Mapped[str]=mapped_column(Text,default='')
    published:Mapped[bool]=mapped_column(Boolean,default=False)
    valid:Mapped[bool]=mapped_column(Boolean,default=True)
    invalidated_reason:Mapped[str]=mapped_column(Text,default='')
    invalidated_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    computed_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    recomputed_from_id:Mapped[int|None]=mapped_column(Integer,nullable=True)
    created_at:Mapped[str]=mapped_column(String(40),default='')
