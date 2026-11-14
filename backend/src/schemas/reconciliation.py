from pydantic import BaseModel
class ReconciliationCreate(BaseModel):
 run_a_id:str
 run_b_id:str
