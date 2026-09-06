"""Completion from live DPS events, calibrated on both Z1 Max models.

a180 emits standby just before done; done lasts about five seconds. a188
emits done after cooling. Never derive completion from standby or time alone.
"""

ACTIVE = frozenset(range(2, 9))
MAX_GAP = 180


def advance(old, values, now):
    """Return serializable state and an optional idempotent event id."""
    state = dict(old or {})
    if values is None:
        return {"at": now, "phase": "unavailable"}, None
    code, error = values[203], values[220]
    if now - state.get("at", now) > MAX_GAP or now < state.get("at", now):
        state = {}
    previous_at = state.get("at", now)
    state["at"] = now
    if error or code not in ACTIVE | {1, 10}:
        return {"at": now, "phase": "idle"}, None
    if code == 1:
        if state.get("phase") == "running":
            state.update(phase="ending", ending_at=now)
        elif state.get("phase") != "ending" or now - state["ending_at"] > 3:
            state = {"at": now, "phase": "idle"}
        return state, None
    if code in ACTIVE:
        if state.get("phase") == "notified":
            return state, None
        if (state.get("phase") not in ("running", "ending")
                or state.get("phase") == "ending" and now - state["ending_at"] > 3):
            state = {"at": now, "phase": "running", "started": now, "active_samples": 1}
        else:
            state["phase"] = "running"
            state["active_samples"] = state.get("active_samples", 0) + (now > previous_at)
            state.pop("ending_at", None)
        return state, None
    # An initial/reconnected done state is an old cycle, never a fresh completion.
    eligible = state.get("phase") == "running" or (
        state.get("phase") == "ending" and now - state["ending_at"] <= 3)
    if eligible and state.get("active_samples", 0) >= 2 and now - state["started"] >= 30:
        state["phase"] = "notified"
        return state, str(int(state["started"] * 1000))
    return state, None


def completion_text(model, name, test=False):
    prefix = "【测试】" if test else ""
    if test:
        return prefix + name + "提醒测试", "通知通道正常。这是模拟通知，没有启动设备，也不表示真实程序已完成。"
    return name + "程序完成", "设备在运行后报告了正常完成信号，且无故障。请确认衣物状态后取出。"
