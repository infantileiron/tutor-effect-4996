from fastapi import APIRouter, Depends
from src.config.database import get_db
from src.utils.security import current_user, editor
from src.schemas.business import (
    EligibilityBatchInput, CandidateInput, CandidateUpdateInput,
    ParticipationInput, CorrectionInput,
)
from src.services import eligibility
from src.controllers.business import serialize, serialize_many
router = APIRouter()


@router.get('/eligibility/batches')
def listing(db=Depends(get_db), user=Depends(current_user)):
    return [eligibility.batch_summary(db, b) for b in eligibility.list_batches(db)]


@router.post('/eligibility/batches', status_code=201)
def create(data: EligibilityBatchInput, db=Depends(get_db), user=Depends(editor)):
    return eligibility.serialize_batch(db, eligibility.create_batch(db, data, user))


@router.get('/eligibility/batches/{id}')
def detail(id: int, db=Depends(get_db), user=Depends(current_user)):
    return eligibility.serialize_batch(db, eligibility.get_batch(db, id))


@router.put('/eligibility/batches/{id}')
def update(id: int, data: EligibilityBatchInput, db=Depends(get_db), user=Depends(editor)):
    return eligibility.serialize_batch(db, eligibility.update_batch(db, id, data, user))


@router.post('/eligibility/batches/{id}/candidates', status_code=201)
def add_candidate(id: int, data: CandidateInput, db=Depends(get_db), user=Depends(editor)):
    return eligibility.upsert_candidate(db, id, data, user)


@router.put('/eligibility/batches/{id}/candidates/{student_id}')
def edit_candidate(id: int, student_id: int, data: CandidateUpdateInput, db=Depends(get_db), user=Depends(editor)):
    payload = CandidateInput(student_id=student_id, **data.model_dump())
    return eligibility.upsert_candidate(db, id, payload, user)


@router.delete('/eligibility/batches/{id}/candidates/{student_id}', status_code=204)
def drop_candidate(id: int, student_id: int, db=Depends(get_db), user=Depends(editor)):
    eligibility.remove_candidate(db, id, student_id, user)


@router.post('/eligibility/batches/{id}/lock')
def lock(id: int, db=Depends(get_db), user=Depends(editor)):
    return eligibility.lock_batch(db, id)


@router.post('/eligibility/batches/{id}/recover')
def recover(id: int, db=Depends(get_db), user=Depends(editor)):
    return eligibility.recover_batch(db, id)


@router.post('/eligibility/batches/{id}/participation')
def participation(id: int, data: ParticipationInput, db=Depends(get_db), user=Depends(editor)):
    return eligibility.record_participation(db, id, data, user)


@router.post('/eligibility/batches/{id}/corrections', status_code=201)
def correction(id: int, data: CorrectionInput, db=Depends(get_db), user=Depends(editor)):
    return eligibility.add_correction(db, id, data, user)


@router.get('/eligibility/batches/{id}/roster')
def roster(id: int, db=Depends(get_db), user=Depends(current_user)):
    payload = eligibility.serialize_batch(db, eligibility.get_batch(db, id))
    return {'basis': payload['basis'], 'roster': payload['roster']}
