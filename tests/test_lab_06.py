"""Відкриті тести задачі 6: Частковий індекс.

Запуск: pytest tests/test_lab_06.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_06.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from dbtools import describe, scans, used_indexes
from labtools import Cases, api, same_rows

T06 = Cases()

QUERY = {
    1: "SELECT id, {f_person}, {f_amount} FROM {fact} WHERE {f_status} = '{open}' AND {f_at} < %(d)s ORDER BY {f_at}",
    2: "SELECT id, {f_item} FROM {fact} WHERE {f_status} = '{open}' AND {f_person} = %(c)s",
    3: "SELECT id, {f_item} FROM {fact} WHERE {f_status} = '{open}' AND {f_at} >= %(d)s ORDER BY {f_at} LIMIT 50",
}

FULL_KEY = {1: "f_at", 2: "f_person", 3: "f_at"}

PARAMS = {1: {"d": "2024-03-01"}, 2: {"c": 57}, 3: {"d": "2024-09-01"}}


def prepare(lab, sset):
    D = lab.use(sset, "fact")
    return D, QUERY[sset].format(**D)


def create(lab, sset, D):
    new = lab.apply_ddl(api(6, sset).call("indexes"), limit=1)
    assert len(new) == 1, "потрібен один частковий індекс"
    lab.sql(f'ANALYZE "{D["fact"]}"')
    return new[0]


def uses_index(lab, sset, params):
    D, text = prepare(lab, sset)
    before = lab.rows(text, params)
    assert before, "тест некоректний: запит без індексу не повернув жодного рядка"
    assert [n["Node Type"] for n in scans(lab.plan(text, params))] == ["Seq Scan"], "до створення індексу план має бути Seq Scan"
    name = create(lab, sset, D)
    plan = lab.plan(text, params)
    nodes = scans(plan)
    assert len(nodes) == 1 and nodes[0]["Node Type"] in ("Index Scan", "Bitmap Heap Scan"), f"очікувалось читання за індексом, а план такий: {describe(plan)}"
    assert used_indexes(plan) == [name], f"запит використав {used_indexes(plan)}, а не ваш індекс {name}: умова запиту має випливати з умови WHERE індексу"
    same_rows(lab.rows(text, params), before, what="результат після створення індексу")
    return D, name


def small(lab, sset, ratio=0.10):
    D, name = uses_index(lab, sset, PARAMS[sset])
    assert lab.index_has_predicate(name), "індекс не частковий: додайте до CREATE INDEX речення WHERE"
    lab.sql(f'CREATE INDEX probe_full ON "{D["fact"]}" ({D["f_status"]}, {D[FULL_KEY[sset]]})')
    mine, full = lab.index_size(name), lab.index_size("probe_full")
    assert mine <= ratio * full, f"індекс займає {mine} байтів, а повний індекс за тими самими стовпцями {full}: частковий має бути щонайменше в {round(1 / ratio)} разів меншим"


@T06.case("S1", public=True)
def uses_partial_s1(lab):
    uses_index(lab, 1, PARAMS[1])


@T06.case("S1", public=True)
def much_smaller_than_full_s1(lab):
    small(lab, 1)


@T06.case("S2", public=True)
def uses_partial_s2(lab):
    uses_index(lab, 2, PARAMS[2])


@T06.case("S2", public=True)
def much_smaller_than_full_s2(lab):
    small(lab, 2)


@T06.case("S3", public=True)
def uses_partial_s3(lab):
    uses_index(lab, 3, PARAMS[3])


@T06.case("S3", public=True)
def much_smaller_than_full_s3(lab):
    small(lab, 3)


@pytest.mark.parametrize("sset,case_fn", T06.params(), ids=T06.ids("T06"))
def test_task_06(lab, sset, case_fn):
    case_fn(lab)
