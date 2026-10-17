"""Відкриті тести задачі 4: Розбір плану EXPLAIN (FORMAT JSON).

Запуск: pytest tests/test_lab_04.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_04.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, api

T04 = Cases()

SCAN_TYPES = ("Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan")


def N(kind, rel=None, idx=None, rows=1, act=None, loops=1, fetches=None, plans=()):
    """Вузол плану у вигляді, який повертає сервер (лише потрібні поля)."""
    node = {"Node Type": kind, "Parallel Aware": False, "Startup Cost": 0.0, "Total Cost": 10.0, "Plan Rows": rows, "Plan Width": 8}
    if rel:
        node["Relation Name"] = rel
        node["Alias"] = rel
    if idx:
        node["Index Name"] = idx
    if act is not None:
        node["Actual Rows"] = act
        node["Actual Loops"] = loops
    if fetches is not None:
        node["Heap Fetches"] = fetches
    if plans:
        node["Plans"] = list(plans)
    return node


def P(root, timing=False):
    out = {"Plan": root}
    if timing:
        out["Planning Time"] = 0.1
        out["Execution Time"] = 1.5
    return [out]


def reference_summary(plan):
    """Незалежна реалізація очікуваного підсумку (прямий обхід плану)."""
    nodes = []

    def walk(n):
        nodes.append(n)
        for c in n.get("Plans", []):
            walk(c)
    walk(plan[0]["Plan"])
    scans = [(n["Node Type"], n["Relation Name"]) for n in nodes if n["Node Type"] in SCAN_TYPES]
    indexes = []
    for n in nodes:
        if "Index Name" in n and n["Index Name"] not in indexes:
            indexes.append(n["Index Name"])
    factors = []
    for n in nodes:
        if "Actual Rows" in n:
            p, a = n["Plan Rows"], n["Actual Rows"]
            factors.append(max(p, a, 1) / max(min(p, a), 1))
    fetches = [n["Heap Fetches"] for n in nodes if "Heap Fetches" in n]
    return {
        "scans": scans,
        "indexes": indexes,
        "has_sort": any(n["Node Type"] in ("Sort", "Incremental Sort") for n in nodes),
        "worst_misestimate": round(max(factors), 2) if factors else None,
        "heap_fetches": sum(fetches) if fetches else None,
    }


def check_for(sset, plan, want=None):
    got = api(4, sset).call("summarize_plan", plan)
    assert isinstance(got, dict), "summarize_plan має повертати словник"
    want = want or reference_summary(plan)
    keys = ("scans", "indexes", "has_sort", "worst_misestimate", "heap_fetches")
    assert set(got) == set(keys), f"ключі словника: отримано {sorted(got)}, очікувалось {sorted(keys)}"
    for key in keys:
        value = got[key]
        if key == "scans":
            value = [tuple(x) for x in value]
        if key == "worst_misestimate" and value is not None:
            assert value == pytest.approx(want[key], abs=0.011), f"worst_misestimate: отримано {value}, очікувалось {want[key]}"
        else:
            assert value == want[key], f"{key}: отримано {value!r}, очікувалось {want[key]!r}"


@T04.case("S1", public=True)
def index_scan_with_actual_rows(lab):
    plan = P(N("Index Scan", "sale", "sale_customer_idx", rows=14, act=13.0), timing=True)
    check_for(1, plan, {"scans": [("Index Scan", "sale")], "indexes": ["sale_customer_idx"], "has_sort": False,
                        "worst_misestimate": 1.08, "heap_fetches": None})


@T04.case("S1", public=True)
def live_seq_scan_and_primary_key(lab):
    D = lab.use(1, "fact")
    full = lab.raw_plan(f'SELECT * FROM "{D["fact"]}"')
    got = api(4, 1).call("summarize_plan", full)
    assert [tuple(x) for x in got["scans"]] == [("Seq Scan", D["fact"])] and got["indexes"] == []
    point = lab.raw_plan(f'SELECT * FROM "{D["fact"]}" WHERE id = 5', analyze=True)
    got = api(4, 1).call("summarize_plan", point)
    assert [tuple(x) for x in got["scans"]] == [("Index Scan", D["fact"])] and got["indexes"] == [f"{D['fact']}_pkey"]
    assert got["worst_misestimate"] == pytest.approx(1.0, abs=0.01)


@T04.case("S2", public=True)
def bitmap_with_sort_without_actual(lab):
    plan = P(N("Sort", rows=10, plans=[
        N("Bitmap Heap Scan", "loan", rows=10, plans=[N("Bitmap Index Scan", None, "loan_returned_idx", rows=10)])]))
    check_for(2, plan, {"scans": [("Bitmap Heap Scan", "loan")], "indexes": ["loan_returned_idx"], "has_sort": True,
                        "worst_misestimate": None, "heap_fetches": None})


@T04.case("S2", public=True)
def live_join_and_sort(lab):
    D = lab.use(2, "item", "fact")
    text = (f'SELECT f.id FROM "{D["fact"]}" f JOIN "{D["item"]}" i ON i.id = f.{D["f_item"]} '
            f'WHERE i.id = 7 ORDER BY f.{D["f_at"]}')
    plan = lab.raw_plan(text, analyze=True)
    check_for(2, plan)
    got = api(4, 2).call("summarize_plan", plan)
    assert got["has_sort"] is True and got["worst_misestimate"] is not None


@T04.case("S3", public=True)
def join_with_index_only_scan(lab):
    plan = P(N("Hash Join", rows=200, act=20, plans=[
        N("Seq Scan", "visit", rows=1000, act=1000),
        N("Hash", rows=5, act=60, plans=[N("Index Only Scan", "workout", "workout_kind_code_idx", rows=5, act=60, fetches=120)])]),
        timing=True)
    check_for(3, plan, {"scans": [("Seq Scan", "visit"), ("Index Only Scan", "workout")], "indexes": ["workout_kind_code_idx"],
                        "has_sort": False, "worst_misestimate": 12.0, "heap_fetches": 120})


@T04.case("S3", public=True)
def live_index_only_after_vacuum(lab):
    D = lab.use(3, "fact")
    lab.sql(f'CREATE INDEX probe_idx ON "{D["fact"]}" ({D["f_person"]}) INCLUDE ({D["f_item"]})')
    lab.sql(f'VACUUM (ANALYZE) "{D["fact"]}"')
    plan = lab.raw_plan(f'SELECT {D["f_item"]} FROM "{D["fact"]}" WHERE {D["f_person"]} = 57', analyze=True)
    got = api(4, 3).call("summarize_plan", plan)
    assert [tuple(x) for x in got["scans"]] == [("Index Only Scan", D["fact"])]
    assert got["indexes"] == ["probe_idx"] and got["heap_fetches"] == 0 and got["has_sort"] is False


@pytest.mark.parametrize("sset,case_fn", T04.params(), ids=T04.ids("T04"))
def test_task_04(lab, sset, case_fn):
    case_fn(lab)
