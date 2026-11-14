from ..services import reconciliation_service
from ..models.reconciliation import RunReconciliation
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,RunReconciliation)
def detail(db,ident):return serialize(require(db,RunReconciliation,ident))
def create(db,body):return serialize(reconciliation_service.create(db,body))
