from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..utils.auth import current,write_user
from ..schemas.reconciliation import ReconciliationCreate
from ..controllers import reconciliation_controller as controller
router=APIRouter(prefix="/reconciliations",tags=["reconciliations"])
@router.get("")
def listing(db=Depends(get_db),user=Depends(current)):return controller.list_all(db)
@router.get("/{ident}")
def detail(ident:str,db=Depends(get_db),user=Depends(current)):return controller.detail(db,ident)
@router.post("",status_code=201)
def create(body:ReconciliationCreate,db=Depends(get_db),user=Depends(write_user)):return controller.create(db,body)
