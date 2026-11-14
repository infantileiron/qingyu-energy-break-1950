from sqlalchemy import String,JSON,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class RunReconciliation(RecordMixin,Base):
 __tablename__="run_reconciliations"
 run_a_id:Mapped[str]=mapped_column(String(36),ForeignKey("runs.id"))
 run_b_id:Mapped[str]=mapped_column(String(36),ForeignKey("runs.id"))
 # 底稿快照在创建时冻结；源运行或源数据随后重算不会改动旧底稿
 snapshot:Mapped[dict]=mapped_column(JSON,default=dict)
