"""Відкриті тести задачі 7: Покривний індекс INCLUDE.

Запуск: pytest tests/test_lab_07.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_07.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from dbtools import describe, scans, walk
from labtools import Cases, api, same_rows

T07 = Cases()

SPEC = {
    1: ("SELECT {f_item}, {f_qty} FROM {fact} WHERE {f_person} = %(c)s", ["f_person"], ["f_item", "f_qty"]),
    2: ("SELECT {f_amount} FROM {fact} WHERE {f_person} = %(c)s AND {f_at} >= %(d)s", ["f_person", "f_at"], ["f_amount"]),
    3: ("SELECT {f_at}, {f_amount} FROM {fact} WHERE {f_person} = %(c)s ORDER BY {f_at}", ["f_person", "f_at"], ["f_amount"]),
}

PARAMS = {1: {"c": 57}, 2: {"c": 57, "d": "2024-05-01"}, 3: {"c": 57}}


def build(lab, sset, params):
    spec, key_cols, include_cols = SPEC[sset]
    D = lab.use(sset, "fact")
    text = spec.format(**D)
    before = lab.rows(text, params)
    assert before, "тест некоректний: запит без індексу не повернув жодного рядка"
    new = lab.apply_ddl(api(7, sset).call("indexes"), limit=1)
    assert len(new) == 1, "потрібен один покривний індекс"
    lab.sql(f'VACUUM (ANALYZE) "{D["fact"]}"')
    return D, text, before, new[0], [D[c] for c in key_cols], [D[c] for c in include_cols]


def index_only(lab, sset, params):
    D, text, before, name, key_cols, include_cols = build(lab, sset, params)
    plan = lab.plan(text, params, analyze=True)
    nodes = scans(plan)
    assert len(nodes) == 1 and nodes[0]["Node Type"] == "Index Only Scan", f"очікувався Index Only Scan, а план такий: {describe(plan)}"
    node = nodes[0]
    assert node["Index Name"] == name, f"використано індекс {node['Index Name']}, а не створений вами {name}"
    assert node.get("Heap Fetches") == 0, f"Heap Fetches = {node.get('Heap Fetches')}: після VACUUM звернень до heap бути не повинно"
    if sset == 3:
        assert not [n for n in walk(plan["Plan"]) if n["Node Type"] in ("Sort", "Incremental Sort")], "порядок рядків має давати сам індекс"
    same_rows(lab.rows(text, params), before, ordered=(sset == 3), what="результат після створення індексу")
    return D, name, key_cols, include_cols


@T07.case("S1", public=True)
def hot_s1(lab):
    index_only(lab, 1, PARAMS[1])


@T07.case("S1", public=True)
def cold_s1(lab):
    index_only(lab, 1, {"c": 14000})


@T07.case("S2", public=True)
def hot_s2(lab):
    index_only(lab, 2, PARAMS[2])


@T07.case("S2", public=True)
def late_start_s2(lab):
    index_only(lab, 2, {"c": 150, "d": "2025-02-01"})


@T07.case("S3", public=True)
def hot_s3(lab):
    index_only(lab, 3, PARAMS[3])


@T07.case("S3", public=True)
def cold_s3(lab):
    index_only(lab, 3, {"c": 11000})


@pytest.mark.parametrize("sset,case_fn", T07.params(), ids=T07.ids("T07"))
def test_task_07(lab, sset, case_fn):
    case_fn(lab)
