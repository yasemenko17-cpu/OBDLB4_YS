"""Відкриті тести задачі 5: Складений індекс.

Запуск: pytest tests/test_lab_05.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_05.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from dbtools import describe, scans, walk
from labtools import Cases, api, same_rows

T05 = Cases()

QUERY = {
    1: ('SELECT id, {f_amount} FROM {fact} WHERE {f_person} = %(c)s AND {f_at} >= %(d1)s AND {f_at} < %(d2)s ORDER BY {f_at}',
        ["f_person"], "f_at"),
    2: ("SELECT id, {f_at} FROM {fact} WHERE {f_person} = %(c)s AND {f_status} = '{done}' ORDER BY {f_at} DESC LIMIT 10",
        ["f_person", "f_status"], "f_at"),
    3: ("SELECT id, {f_amount} FROM {fact} WHERE {f_person} = %(c)s AND {f_status} = '{done}' AND {f_at} >= %(d1)s ORDER BY {f_at}",
        ["f_person", "f_status"], "f_at"),
}

HOT = {1: 57, 2: 57, 3: 57}

COLD = {1: 15000, 2: 11000, 3: 9000}

RANGE = {"d1": "2024-05-01", "d2": "2024-06-01"}

FULL = {"d1": "2024-01-01", "d2": "2026-01-01"}


def run(lab, sset, params, form=QUERY, limit=2):
    spec, eq_cols, order_col = form[sset]
    D = lab.use(sset, "fact")
    text = spec.format(**D)
    eq = {D[c] for c in eq_cols}
    before = lab.rows(text, params)
    assert before, "тест некоректний: запит без індексу не повернув жодного рядка"
    first = scans(lab.plan(text, params))
    assert [n["Node Type"] for n in first] == ["Seq Scan"], "до створення індексу план має бути Seq Scan"
    new = lab.apply_ddl(api(5, sset).call("indexes"), limit=limit)
    assert new, "список команд не створив жодного індексу"
    lab.sql(f'ANALYZE "{D["fact"]}"')
    plan = lab.plan(text, params)
    found = scans(plan)
    assert len(found) == 1 and found[0]["Node Type"] == "Index Scan", \
        f"очікувався один вузол Index Scan, а план такий: {describe(plan)}"
    node = found[0]
    assert node["Index Name"] in new, f"запит використав індекс {node['Index Name']}, який не створено вашими командами"
    assert not [n for n in walk(plan["Plan"]) if n["Node Type"] in ("Sort", "Incremental Sort")], \
        f"у плані є вузол сортування: індекс має віддавати рядки вже впорядкованими. План: {describe(plan)}"
    keys = [c for c, is_key in lab.index_columns(node["Index Name"]) if is_key]
    lead = set(keys[:len(eq)])
    assert lead == eq, f"ведучі стовпці індексу {keys}: спершу мають іти стовпці з умовами рівності {sorted(eq)}"
    assert keys[len(eq)] == D[order_col], f"після стовпців рівності має йти стовпець діапазону й сортування {D[order_col]}; ключ індексу {keys}"
    assert "Filter" not in node, f"умова {node.get('Filter')} перевіряється фільтром після читання індексу: її слід винести в ключ"
    same_rows(lab.rows(text, params), before, ordered=True, what="результат запиту після створення індексу")
    return plan


@T05.case("S1", public=True)
def hot_customer_s1(lab):
    run(lab, 1, {"c": HOT[1], **RANGE})


@T05.case("S1", public=True)
def cold_customer_s1(lab):
    run(lab, 1, {"c": COLD[1], **FULL})


@T05.case("S2", public=True)
def hot_reader_s2(lab):
    run(lab, 2, {"c": HOT[2]})


@T05.case("S2", public=True)
def cold_reader_s2(lab):
    run(lab, 2, {"c": COLD[2]})


@T05.case("S3", public=True)
def hot_member_s3(lab):
    run(lab, 3, {"c": HOT[3], "d1": "2024-06-01"})


@T05.case("S3", public=True)
def cold_member_s3(lab):
    run(lab, 3, {"c": COLD[3], "d1": "2024-02-01"})


@pytest.mark.parametrize("sset,case_fn", T05.params(), ids=T05.ids("T05"))
def test_task_05(lab, sset, case_fn):
    case_fn(lab)
