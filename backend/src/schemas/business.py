from typing import Literal
from pydantic import BaseModel,Field,model_validator
class LoginInput(BaseModel):
    email:str=Field(max_length=120)
    password:str=Field(max_length=200)
class StudentInput(BaseModel):
    code:str=Field(min_length=1,max_length=50)
    name:str=Field(min_length=1,max_length=80)
    campus:str=Field(min_length=1,max_length=50)
    group:Literal['control','intervention']
    score:float|None=Field(default=None,ge=0,le=100,allow_inf_nan=False)
    absent:bool=False
    @model_validator(mode='after')
    def score_required(self):
        if not self.absent and self.score is None: raise ValueError('非缺考学员必须填写成绩')
        return self
class PlanInput(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    campus:str=Field(default='全部',max_length=50)
    exclude_absent:bool=True
    description:str=Field(default='',max_length=2000)
class RunInput(BaseModel):
    plan_id:int=Field(gt=0)
class ConclusionInput(BaseModel):
    conclusion:str=Field(min_length=4,max_length=3000)
    published:bool=False

class EligibilityBatchInput(BaseModel):
    title:str=Field(min_length=2,max_length=120)
    term:str=Field(default='',max_length=80)
    threshold:float=Field(ge=0,le=100,allow_inf_nan=False)
    direction:Literal['gte','lte']='gte'
    bandwidth:float|None=Field(default=None,gt=0,le=100,allow_inf_nan=False)
    bandwidth_rule:Literal['auto_min_side_n','manual']='auto_min_side_n'
    min_side_n:int=Field(default=5,ge=3,le=200)
    min_side_distinct:int=Field(default=5,ge=3,le=100)
    min_participation_jump:float=Field(default=0.2,ge=0.01,le=0.99)
    description:str=Field(default='',max_length=2000)
    @model_validator(mode='after')
    def manual_bandwidth(self):
        if self.bandwidth_rule=='manual' and self.bandwidth is None: raise ValueError('手动带宽规则必须填写带宽')
        return self

class CandidateInput(BaseModel):
    student_id:int=Field(gt=0)
    enrollment_score:float=Field(ge=0,le=100,allow_inf_nan=False)
    name:str|None=Field(default=None,max_length=80)
    campus:str|None=Field(default=None,max_length=50)
    code:str|None=Field(default=None,max_length=50)

class CandidateUpdateInput(BaseModel):
    enrollment_score:float=Field(ge=0,le=100,allow_inf_nan=False)
    name:str|None=Field(default=None,max_length=80)
    campus:str|None=Field(default=None,max_length=50)
    code:str|None=Field(default=None,max_length=50)

class ParticipationInput(BaseModel):
    student_id:int=Field(gt=0)
    participated:bool
    note:str=Field(default='',max_length=500)

class CorrectionInput(BaseModel):
    field:Literal['enrollment_score','threshold','direction','participation']
    new_value:object=None
    student_id:int|None=Field(default=None,gt=0)
    note:str=Field(default='',max_length=500)

class RdRunInput(BaseModel):
    batch_id:int=Field(gt=0)
