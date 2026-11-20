"""In-process serialization keys.

The database row locks (SELECT ... FOR UPDATE) are the cross-process guard.
This small registry also serializes same-process callers, including SQLite
test runs where FOR UPDATE is a no-op.
"""
import threading
from collections import defaultdict
_guard=threading.Lock()
_locks:dict[int,threading.RLock]=defaultdict(threading.RLock)

def batch_lock(batch_id:int)->threading.RLock:
    with _guard:
        return _locks[int(batch_id)]
