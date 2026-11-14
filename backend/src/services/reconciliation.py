"""运行对账：把两次运行在共同有效小时上的总电量差，拆为产量贡献与单位能耗贡献。

配对口径：按归一化到 UTC 的小时时刻配对，只保留两侧均为有效运行观测的小时；
单边观测（仅一侧有效、另一侧缺测或被隔离）单列，不参与归因。

归因方法（Shapley 对称平均，即两种替换顺序的平均）：
对每个共同小时 t，记 A 侧 (o_A, u_A)、B 侧 (o_B, u_B)，电量 e = o × u。
  顺序1（先换产量，后换单位能耗）：
    产量项 = (o_B - o_A) × u_A
    能耗项 = o_B × (u_B - u_A)
  顺序2（先换单位能耗，后换产量）：
    产量项 = (o_B - o_A) × u_B
    能耗项 = o_A × (u_B - u_A)
  取两种顺序的平均，两项之和恒等于 e_B - e_A，且对 A/B 互换反对称。
"""
import math
from .readings import parse_time

EXCLUSION_REASONS = ("stopped", "zero_output", "missing_measurement")


def _hour_key(timestamp):
    """带时区时刻统一转 UTC 的 ISO 字符串作为配对键，跨时区等价时刻落在同一键。"""
    return parse_time(timestamp).isoformat()


def _valid_index(observations):
    index = {}
    for obs in observations:
        index[_hour_key(obs["timestamp"])] = obs
    return index


def _excluded_index(excluded):
    index = {}
    for item in excluded:
        index[_hour_key(item["timestamp"])] = item.get("reason", "missing_measurement")
    return index


def reconcile(result_a, result_b):
    """对两份运行 result 快照做逐时对账，返回可直接持久化的底稿字典。"""
    obs_a = _valid_index(result_a.get("observations", []))
    obs_b = _valid_index(result_b.get("observations", []))
    ex_a = _excluded_index(result_a.get("excluded", []))
    ex_b = _excluded_index(result_b.get("excluded", []))

    common_keys = sorted(set(obs_a) & set(obs_b))
    # 非共同小时：只要某侧在该时刻存在记录（有效或隔离），就在该侧单边列出
    all_a = set(obs_a) | set(ex_a)
    all_b = set(obs_b) | set(ex_b)
    only_a_keys = sorted(all_a - set(common_keys))
    only_b_keys = sorted(all_b - set(common_keys))

    hourly = []
    sum_kwh_a = sum_kwh_b = 0.0
    sum_output_a = sum_output_b = 0.0
    sum_output_effect = sum_intensity_effect = 0.0
    for key in common_keys:
        a, b = obs_a[key], obs_b[key]
        o_a, u_a = float(a["output_kg"]), float(a["intensity"])
        o_b, u_b = float(b["output_kg"]), float(b["intensity"])
        e_a, e_b = float(a["kwh"]), float(b["kwh"])
        # 顺序1：产量先替换（用 A 的单位能耗），单位能耗后替换（用 B 的产量）
        output_1 = (o_b - o_a) * u_a
        intensity_1 = o_b * (u_b - u_a)
        # 顺序2：单位能耗先替换（用 A 的产量），产量后替换（用 B 的单位能耗）
        intensity_2 = o_a * (u_b - u_a)
        output_2 = (o_b - o_a) * u_b
        output_effect = (output_1 + output_2) / 2.0
        intensity_effect = (intensity_1 + intensity_2) / 2.0
        delta = e_b - e_a
        hourly.append({
            "timestamp": key,
            "kwh_a": e_a,
            "kwh_b": e_b,
            "kwh_delta": delta,
            "output_a_kg": o_a,
            "output_b_kg": o_b,
            "intensity_a": u_a,
            "intensity_b": u_b,
            "output_effect": output_effect,
            "intensity_effect": intensity_effect,
            "residual": delta - output_effect - intensity_effect,
        })
        sum_kwh_a += e_a
        sum_kwh_b += e_b
        sum_output_a += o_a
        sum_output_b += o_b
        sum_output_effect += output_effect
        sum_intensity_effect += intensity_effect

    def single_side(keys, present_obs, present_ex, other_obs, other_ex, side):
        rows = []
        for key in keys:
            if key in present_obs:
                obs = present_obs[key]
                rows.append({"timestamp": key, "side": side, "state": "valid",
                             "reason": "", "kwh": float(obs["kwh"]),
                             "output_kg": float(obs["output_kg"])})
            else:
                rows.append({"timestamp": key, "side": side, "state": "excluded",
                             "reason": present_ex.get(key, "missing_measurement"),
                             "kwh": None, "output_kg": None})
        return rows

    only_a = single_side(only_a_keys, obs_a, ex_a, obs_b, ex_b, "a")
    only_b = single_side(only_b_keys, obs_b, ex_b, obs_a, ex_a, "b")

    total_delta = sum_kwh_b - sum_kwh_a
    attributed = sum_output_effect + sum_intensity_effect
    return {
        "schema_version": 1,
        "common_count": len(common_keys),
        "hourly": hourly,
        "only_a": only_a,
        "only_b": only_b,
        "only_a_count": len(only_a),
        "only_b_count": len(only_b),
        "totals": {
            "kwh_a": sum_kwh_a,
            "kwh_b": sum_kwh_b,
            "kwh_delta": total_delta,
            "output_a_kg": sum_output_a,
            "output_b_kg": sum_output_b,
            "output_effect": sum_output_effect,
            "intensity_effect": sum_intensity_effect,
            "attributed_delta": attributed,
            "unattributed_kwh": total_delta - attributed,
        },
        "has_common_hours": bool(common_keys),
    }
