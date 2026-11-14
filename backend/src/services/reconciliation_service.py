from uuid import uuid4
from fastapi import HTTPException
from ..models.run import ChangeRun
from ..models.reconciliation import RunReconciliation
from .reconciliation import reconcile


def _completed_run(db, run_id, label):
    run = db.get(ChangeRun, run_id)
    if run is None:
        raise HTTPException(404, f"{label}运行不存在")
    if run.status != "completed":
        raise HTTPException(409, f"{label}运行尚未完成，无法对账")
    result = run.result or {}
    if "observations" not in result:
        raise HTTPException(409, f"{label}运行缺少有效观测底稿（旧版本结果），无法对账")
    return run


def create(db, body):
    if body.run_a_id == body.run_b_id:
        raise HTTPException(422, "对账需要选择两条不同的运行")
    run_a = _completed_run(db, body.run_a_id, "基准侧")
    run_b = _completed_run(db, body.run_b_id, "对比侧")
    # 冻结创建时刻的两份结果；之后源数据更新、运行重算都不改写本底稿
    result_a = run_a.result
    result_b = run_b.result
    ledger = reconcile(result_a, result_b)
    snapshot = {
        "run_a_id": run_a.id,
        "run_b_id": run_b.id,
        "run_a_label": result_a.get("dataset_name", run_a.id),
        "run_b_label": result_b.get("dataset_name", run_b.id),
        "frozen_run_a": {"id": run_a.id, "created_at": run_a.created_at.isoformat() + "Z",
                         "valid_count": result_a.get("valid_count"),
                         "excluded_count": result_a.get("excluded_count")},
        "frozen_run_b": {"id": run_b.id, "created_at": run_b.created_at.isoformat() + "Z",
                         "valid_count": result_b.get("valid_count"),
                         "excluded_count": result_b.get("excluded_count")},
        "ledger": ledger,
    }
    row = RunReconciliation(id=str(uuid4()), run_a_id=run_a.id, run_b_id=run_b.id,
                            snapshot=snapshot)
    db.add(row)
    db.commit()
    return row
