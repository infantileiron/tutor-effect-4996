import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('DATABASE_URL', 'sqlite:///' + tempfile.mkstemp(suffix='.db')[1])
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/15')
os.environ.setdefault('JWT_SECRET', 'test-secret')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import database
from src.models.entities import Base


class FakeQueue:
    def __init__(self):
        self.items = []

    def lpush(self, key, value):
        self.items.append((key, value))

    def ping(self):
        return True

    def brpop(self, key, timeout=0):
        return None


@pytest.fixture()
def db_factory(tmp_path):
    path = tmp_path / 'test.db'
    engine = create_engine('sqlite:///' + str(path), connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    database.engine = engine
    database.SessionLocal = factory
    yield factory
    engine.dispose()


@pytest.fixture()
def app_client(db_factory, monkeypatch):
    from src import main
    from src.services import rd_reports, reports
    import scripts.seed_demo as seed_demo
    fake = FakeQueue()
    started = {}

    def fake_seed():
        if started.get('seeded'):
            return
        started['seeded'] = True
        from src.models.entities import User, Student
        from src.utils.security import hash_password
        from src.config.database import SessionLocal
        with SessionLocal() as db:
            for role in ('admin', 'analyst', 'viewer'):
                db.add(User(email=role + '@demo.local', role=role, password_hash=hash_password('Demo123!')))
            db.commit()
        seed_demo.seed()

    monkeypatch.setenv('SEED_DEMO', 'false')
    monkeypatch.setattr(rd_reports, 'queue', fake)
    monkeypatch.setattr(reports, 'queue', fake)
    monkeypatch.setattr(main, 'SessionLocal', db_factory)
    monkeypatch.setattr(database, 'SessionLocal', db_factory)
    monkeypatch.setattr(database, 'engine', db_factory.kw['bind'])
    monkeypatch.setattr(main, 'queue', fake, raising=False)
    monkeypatch.setattr(seed_demo, 'SessionLocal', db_factory)
    main.SessionLocal = db_factory
    import src.config.database as cfg
    cfg.SessionLocal = db_factory
    with TestClient(main.app) as client:
        # seed manually: create users and a small deterministic sample set
        with db_factory() as db:
            from src.models.entities import User, Student
            from src.utils.security import hash_password
            for role in ('admin', 'analyst', 'viewer'):
                db.add(User(email=role + '@demo.local', role=role, password_hash=hash_password('Demo123!')))
            _seed_students(db)
            db.commit()
        yield client
    main.SessionLocal = database.SessionLocal


@pytest.fixture()
def client(app_client):
    return app_client


def _seed_students(db):
    """Deterministic sample: enrolment 40..80, tutoring above 60."""
    from src.models.entities import Student
    import random
    rng = random.Random(7)
    for i in range(240):
        enrol = round(30 + 50 * (i / 239), 1)
        eligible = enrol >= 60
        participated = (i % 10 != 0) if eligible else (i % 5 == 0)
        outcome = 55 + 0.4 * enrol + (6 if participated else 0) + rng.gauss(0, 3.5)
        outcome = round(max(0, min(100, outcome)), 1)
        db.add(Student(code=f'C{i:03d}', name=f'候选人{i:03d}', campus=['城东', '城西', '滨江', '高新'][i % 4],
                       group='control', score=outcome, absent=False))
