import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.reconciliation import reconcile  # noqa: E402


def _ts(hour):
    return (datetime(2026, 10, 1, tzinfo=timezone.utc)
            + timedelta(hours=hour)).isoformat()


def make_result(rows):
    """rows: (hour, kwh, output) 有效观测列表。"""
    observations = []
    for hour, kwh, output in rows:
        observations.append({
            "timestamp": _ts(hour),
            "status": "running", "kwh": kwh, "output_kg": output,
            "intensity": kwh / output,
        })
    return {"observations": observations, "excluded": [],
            "valid_count": len(observations), "excluded_count": 0}


def test_identity_hourly_sums_equal_total_delta():
    # 产量与单位能耗同时变化，逐时两项贡献之和恒等于逐时电量差，合计等于总差额
    a = make_result([(h, 100.0 + h, 40.0) for h in range(10)])
    b = make_result([(h, 130.0 + 2 * h, 50.0 + h) for h in range(10)])
    ledger = reconcile(a, b)
    assert ledger["common_count"] == 10
    for row in ledger["hourly"]:
        assert abs(row["output_effect"] + row["intensity_effect"]
                   - row["kwh_delta"]) < 1e-9
        assert abs(row["residual"]) < 1e-9
    totals = ledger["totals"]
    assert abs(totals["kwh_delta"] - (totals["kwh_b"] - totals["kwh_a"])) < 1e-9
    assert abs(totals["output_effect"] + totals["intensity_effect"]
               - totals["kwh_delta"]) < 1e-9
    assert abs(totals["unattributed_kwh"]) < 1e-9


def test_pure_output_change_has_zero_intensity_effect():
    # 单位能耗不变，仅产量翻倍：电量差应全部归为产量贡献
    a = make_result([(h, 100.0, 40.0) for h in range(8)])
    b = make_result([(h, 200.0, 80.0) for h in range(8)])
    ledger = reconcile(a, b)
    totals = ledger["totals"]
    assert abs(totals["intensity_effect"]) < 1e-9
    assert abs(totals["output_effect"] - 800.0) < 1e-9
    assert abs(totals["kwh_delta"] - 800.0) < 1e-9


def test_pure_intensity_change_has_zero_output_effect():
    # 产量不变，仅单位能耗上升：电量差应全部归为单位能耗贡献
    a = make_result([(h, 100.0, 40.0) for h in range(8)])
    b = make_result([(h, 150.0, 40.0) for h in range(8)])
    ledger = reconcile(a, b)
    totals = ledger["totals"]
    assert abs(totals["output_effect"]) < 1e-9
    assert abs(totals["intensity_effect"] - 400.0) < 1e-9
    assert abs(totals["kwh_delta"] - 400.0) < 1e-9


def test_swap_sides_is_antisymmetric():
    # 双方互换：所有差额与贡献项精确反号，共同小时集合不变
    a = make_result([(h, 100.0 + h * 3, 40.0 + h) for h in range(12)])
    b = make_result([(h, 90.0 + h * 4, 35.0 + 2 * h) for h in range(12)])
    ab = reconcile(a, b)
    ba = reconcile(b, a)
    assert ab["common_count"] == ba["common_count"] == 12
    for r1, r2 in zip(ab["hourly"], ba["hourly"]):
        assert r1["timestamp"] == r2["timestamp"]
        assert abs(r1["kwh_delta"] + r2["kwh_delta"]) < 1e-9
        assert abs(r1["output_effect"] + r2["output_effect"]) < 1e-9
        assert abs(r1["intensity_effect"] + r2["intensity_effect"]) < 1e-9
    t1, t2 = ab["totals"], ba["totals"]
    assert abs(t1["kwh_delta"] + t2["kwh_delta"]) < 1e-9
    assert abs(t1["output_effect"] + t2["output_effect"]) < 1e-9
    assert abs(t1["intensity_effect"] + t2["intensity_effect"]) < 1e-9


def test_timezone_equivalent_timestamps_pair():
    # 同一时刻的不同时区表示（+09:00 与 UTC）必须配为同一共同小时
    a = {"observations": [
        {"timestamp": "2026-10-01T09:00:00+09:00", "status": "running",
         "kwh": 100.0, "output_kg": 40.0, "intensity": 2.5},
        {"timestamp": "2026-10-01T01:00:00+00:00", "status": "running",
         "kwh": 110.0, "output_kg": 44.0, "intensity": 2.5},
    ], "excluded": []}
    b = {"observations": [
        {"timestamp": "2026-10-01T00:00:00+00:00", "status": "running",
         "kwh": 120.0, "output_kg": 48.0, "intensity": 2.5},
        {"timestamp": "2026-10-01T10:00:00+09:00", "status": "running",
         "kwh": 130.0, "output_kg": 52.0, "intensity": 2.5},
    ], "excluded": []}
    ledger = reconcile(a, b)
    assert ledger["common_count"] == 2
    assert ledger["hourly"][0]["timestamp"] == "2026-10-01T00:00:00+00:00"
    assert ledger["hourly"][1]["timestamp"] == "2026-10-01T01:00:00+00:00"
    assert ledger["only_a_count"] == 0 and ledger["only_b_count"] == 0


def test_sample_added_and_removed_listed_separately():
    # B 新增 12 点；A 独有 08 点；09 点 A 有效、B 被隔离——均单列且不参与归因
    a = make_result([(h, 100.0, 40.0) for h in range(10)])
    b_rows = [(h, 105.0, 42.0) for h in range(9)] + [(12, 90.0, 30.0)]
    b = make_result(b_rows)
    b["excluded"] = [{"timestamp": _ts(9), "reason": "stopped"}]
    ledger = reconcile(a, b)
    assert ledger["common_count"] == 9
    only_a = {r["timestamp"]: r for r in ledger["only_a"]}
    only_b = {r["timestamp"]: r for r in ledger["only_b"]}
    assert _ts(9) in only_a
    assert only_a[_ts(9)]["state"] == "valid"
    assert _ts(12) in only_b
    assert only_b[_ts(12)]["state"] == "valid"
    # 单边小时不进入逐时归因
    assert all(r["timestamp"] != _ts(12) for r in ledger["hourly"])
    # B 侧隔离观测也单列，保留原因
    b_excluded_only = [r for r in ledger["only_b"] if r["timestamp"] == _ts(9)]
    assert b_excluded_only and b_excluded_only[0]["state"] == "excluded"
    assert b_excluded_only[0]["reason"] == "stopped"
    # 总差额只统计共同小时
    assert abs(ledger["totals"]["kwh_delta"] - 9 * 5.0) < 1e-9


def test_no_common_hours_flags_and_zero_totals():
    a = make_result([(h, 100.0, 40.0) for h in range(8)])
    b = make_result([(h, 100.0, 40.0) for h in range(20, 28)])
    ledger = reconcile(a, b)
    assert ledger["has_common_hours"] is False
    assert ledger["common_count"] == 0
    assert ledger["hourly"] == []
    assert ledger["only_a_count"] == 8 and ledger["only_b_count"] == 8
    assert ledger["totals"]["kwh_delta"] == 0.0
    assert ledger["totals"]["output_effect"] == 0.0
    assert ledger["totals"]["intensity_effect"] == 0.0


def test_shapley_average_equals_half_of_two_orderings():
    # 构造产量与能耗都变化的小时，手工核对两种替换顺序的平均
    o_a, u_a = 40.0, 2.5
    o_b, u_b = 50.0, 3.0
    a = make_result([(0, o_a * u_a, o_a)])
    b = make_result([(0, o_b * u_b, o_b)])
    ledger = reconcile(a, b)
    row = ledger["hourly"][0]
    output_1 = (o_b - o_a) * u_a
    output_2 = (o_b - o_a) * u_b
    intensity_1 = o_b * (u_b - u_a)
    intensity_2 = o_a * (u_b - u_a)
    assert abs(row["output_effect"] - (output_1 + output_2) / 2) < 1e-12
    assert abs(row["intensity_effect"]
               - (intensity_1 + intensity_2) / 2) < 1e-12
    assert abs(row["kwh_delta"] - (o_b * u_b - o_a * u_a)) < 1e-12
