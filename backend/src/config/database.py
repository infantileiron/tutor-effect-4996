import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
_url=os.environ['DATABASE_URL']
_engine_kwargs={'pool_pre_ping':True}
if _url.startswith('sqlite'):
    _engine_kwargs['connect_args']={'check_same_thread':False,'timeout':30}
engine=create_engine(_url,**_engine_kwargs)
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
class Base(DeclarativeBase): pass
def get_db():
    with SessionLocal() as db: yield db
