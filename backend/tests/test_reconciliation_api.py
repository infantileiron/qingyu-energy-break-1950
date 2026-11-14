import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import database as db_config  # noqa: E402
from src.config.database import Base, get_db  # noqa: E402
from src.main import app  # noqa: E402
from src.middlewares import audit as audit_mw  # noqa: E402
from src.models.run import ChangeRun  # noqa: E402
from src.models.user import User  # noqa: E402
from src.models.reconciliation import RunReconciliation  # noqa: E402
from src.utils.security import hash_password, issue  # noqa: E402

test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, expire_on_commit=False)


def _ts(hour):
    return (datetime(2026, 10, 1, tzinfo=timezone.utc)
            + timedelta(hours=hour)).isoformat()


def _result(rows, excluded=None, name="窑A"):
    observations = [{"timestamp": _ts(h), "status": "running", "kwh": k,
                     "output_kg": o, "intensity": k / o} for h, k, o in rows]
    return {"observations": observations, "excluded": excluded or [],
            "valid_count": len(observations),
            "excluded_count": len(excluded or []), "dataset_name": name,
            "changes": {"segments": [], "change_indices": [], "objective": 0.0},
            "robust": {}, "window_name": "w", "config": {}}


@pytest.fixture()
def client(monkeypatch):
    # 让应用各处（get_db 依赖与审计中间件）都使用同一个内存库
    monkeypatch.setattr(db_config, "engine", test_engine)
    monkeypatch.setattr(db_config, "Session", TestSession)
    monkeypatch.setattr(audit_mw, "Session", TestSession)
    Base.metadata.create_all(test_engine)
    app.dependency_overrides[get_db] = lambda: (yield from _session_iter())
    with TestSession() as db:
        db.add(User(id="u1", email="analyst@energy.demo", role="analyst",
                    password_hash=hash_password("x")))
        db.add(User(id="u2", email="viewer@energy.demo", role="viewer",
                    password_hash=hash_password("x")))
        db.add(ChangeRun(id="run-a", study_id="s", status="completed",
                         result=_result([(h, 100.0, 40.0) for h in range(10)])))
        db.add(ChangeRun(id="run-b", study_id="s", status="completed",
                         result=_result([(h, 130.0, 50.0) for h in range(10)],
                                        name="窑B")))
        db.add(ChangeRun(id="run-legacy", study_id="s", status="completed",
                         result={}))
        db.add(ChangeRun(id="run-queued", study_id="s", status="queued",
                         result={}))
        db.commit()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)


def _session_iter():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _token(email):
    with TestSession() as db:
        token = issue(db.query(User).filter_by(email=email).one())
    return token


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_reconcile_endpoint_identity_and_listing(client):
    token = _token("analyst@energy.demo")
    r = client.post("/reconciliations",
                    json={"run_a_id": "run-a", "run_b_id": "run-b"},
                    headers=_auth(token))
    assert r.status_code == 201, r.text
    body = r.json()
    ledger = body["snapshot"]["ledger"]
    assert ledger["common_count"] == 10
    totals = ledger["totals"]
    assert abs(totals["output_effect"] + totals["intensity_effect"]
               - totals["kwh_delta"]) < 1e-9
    # 列表与详情可读
    listing = client.get("/reconciliations", headers=_auth(token)).json()
    assert listing[0]["id"] == body["id"]
    detail = client.get(f"/reconciliations/{body['id']}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["snapshot"]["run_a_id"] == "run-a"


def test_snapshot_frozen_when_source_run_recomputed(client):
    token = _token("analyst@energy.demo")
    created = client.post("/reconciliations",
                          json={"run_a_id": "run-a", "run_b_id": "run-b"},
                          headers=_auth(token)).json()
    before = created["snapshot"]["ledger"]["totals"]["kwh_b"]
    # 源数据更新后重算 run-b：电量整体改写
    with TestSession() as db:
        run = db.get(ChangeRun, "run-b")
        run.result = _result([(h, 999.0, 50.0) for h in range(10)], name="窑B")
        db.commit()
    detail = client.get(f"/reconciliations/{created['id']}",
                        headers=_auth(token)).json()
    assert detail["snapshot"]["ledger"]["totals"]["kwh_b"] == before
    with TestSession() as db:
        assert db.query(RunReconciliation).count() == 1


def test_viewer_forbidden_and_auth_required(client):
    r = client.post("/reconciliations",
                    json={"run_a_id": "run-a", "run_b_id": "run-b"},
                    headers=_auth(_token("viewer@energy.demo")))
    assert r.status_code == 403
    assert client.post("/reconciliations",
                       json={"run_a_id": "run-a", "run_b_id": "run-b"}
                       ).status_code == 401


def test_legacy_run_and_queued_run_rejected(client):
    token = _token("analyst@energy.demo")
    r1 = client.post("/reconciliations",
                     json={"run_a_id": "run-legacy", "run_b_id": "run-b"},
                     headers=_auth(token))
    assert r1.status_code == 409 and "旧版本" in r1.json()["detail"]
    r2 = client.post("/reconciliations",
                     json={"run_a_id": "run-a", "run_b_id": "run-queued"},
                     headers=_auth(token))
    assert r2.status_code == 409
    r3 = client.post("/reconciliations",
                     json={"run_a_id": "run-a", "run_b_id": "run-a"},
                     headers=_auth(token))
    assert r3.status_code == 422
    r4 = client.post("/reconciliations",
                     json={"run_a_id": "missing", "run_b_id": "run-b"},
                     headers=_auth(token))
    assert r4.status_code == 404


def test_no_common_hours_explicit_message(client):
    with TestSession() as db:
        db.add(ChangeRun(id="run-other", study_id="s", status="completed",
                         result=_result([(h, 100.0, 40.0)
                                         for h in range(20, 28)])))
        db.commit()
    r = client.post("/reconciliations",
                    json={"run_a_id": "run-a", "run_b_id": "run-other"},
                    headers=_auth(_token("analyst@energy.demo")))
    assert r.status_code == 201
    ledger = r.json()["snapshot"]["ledger"]
    assert ledger["has_common_hours"] is False
    assert ledger["common_count"] == 0
    assert ledger["only_a_count"] == 10 and ledger["only_b_count"] == 8


def test_swap_endpoint_antisymmetric(client):
    token = _token("analyst@energy.demo")
    ab = client.post("/reconciliations",
                     json={"run_a_id": "run-a", "run_b_id": "run-b"},
                     headers=_auth(token)).json()["snapshot"]["ledger"]
    ba = client.post("/reconciliations",
                     json={"run_a_id": "run-b", "run_b_id": "run-a"},
                     headers=_auth(token)).json()["snapshot"]["ledger"]
    assert abs(ab["totals"]["kwh_delta"] + ba["totals"]["kwh_delta"]) < 1e-9
    assert abs(ab["totals"]["output_effect"]
               + ba["totals"]["output_effect"]) < 1e-9
    assert abs(ab["totals"]["intensity_effect"]
               + ba["totals"]["intensity_effect"]) < 1e-9
