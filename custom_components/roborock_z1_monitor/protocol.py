"""Model/schema guards for the three verified read-only data points."""

DOMAIN = "roborock_z1_monitor"
SOURCE_ENTRY = "source_entry"
MODELS = {"roborock.wm.a180": "洗衣机 Z1 Max", "roborock.cd.a188": "干衣机 Z1 Max"}
FIELDS = {203: "status", 218: "washing_left", 220: "error"}
START_FIELDS = {204: "mode", 205: "program", 209: "spin_level"}


def supports_start(product):
    """Fail closed on model or control schema drift; preserve read-only monitoring."""
    if product.get("model") not in MODELS:
        return False
    item = next((x for x in product.get("schema", []) if x.get("id") == 200), {})
    schema = {x.get("id"): x for x in product.get("schema", [])}
    return (item.get("code") == "start" and item.get("mode") == "rw" and item.get("type") == "BOOL"
            and all(schema.get(k, {}).get("code") == code
                    and schema[k].get("mode") == "rw" and schema[k].get("type") == "VALUE"
                    for k, code in START_FIELDS.items()))


def start_payload(values):
    """Only start from a freshly queried, fault-free standby state.

    DP 200 = 1 matches HA's RoborockButtonEntityA01 implementation. Never
    write factory controls, locks, parameters, or automatically retry a start.
    """
    base = validate_values(values)
    if base[203] != 1 or base[220] != 0:
        raise ValueError("只能在待机且无故障时启动，请先在石头 App 检查设备")
    if any(type(values.get(k)) is not int or values[k] <= 0 for k in START_FIELDS):
        raise ValueError("当前程序参数不完整，已取消启动")
    # Verified on a180/a188: a bare START may restore prior/default parameters.
    # Snapshot and send these fields in the SAME packet, with START last.
    return {**{k: values[k] for k in START_FIELDS}, 200: 1}


def validate_schema(product):
    if product.get("model") not in MODELS:
        raise ValueError("Unsupported model")
    schema = {item["id"]: item for item in product.get("schema", [])}
    for key, code in FIELDS.items():
        item = schema.get(key, {})
        if item.get("code") != code or item.get("mode") != "ro" or item.get("type") != "VALUE":
            raise ValueError("Unexpected read-only schema")
    if schema.get(10000, {}).get("code") != "id_query":
        raise ValueError("Missing query operation")


def validate_values(values):
    result = {}
    for key in FIELDS:
        value = values.get(key)
        # Keep raw device numbers; do not silently substitute unavailable with zero.
        if type(value) is not int or value < 0:
            raise ValueError("Missing or invalid device response")
        result[key] = value
    return result
