"""Відкриті тести задачі 8: Індекс за виразом або переписування запиту.

Запуск: pytest tests/test_lab_08.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_08.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from dbtools import describe, scans
from labtools import Cases, api, same_rows

T08 = Cases()

SLOW = {
    1: ("SELECT id FROM {person} WHERE lower({p_email}) = lower(%(v)s) ORDER BY id", "person"),
    2: ("SELECT id FROM {fact} WHERE date_trunc('day', {f_at}) = %(v)s ORDER BY id", "fact"),
    3: ("SELECT id FROM {fact} WHERE ({f_attrs} ->> 'sku') = %(v)s ORDER BY id", "fact"),
}


def prepare(lab, sset):
    spec, role = SLOW[sset]
    D = lab.use(sset, role)
    if sset == 2:  # у наборі 2 уже є звичайний індекс за датою: розв'язок може обійтися без нового індексу
        lab.sql(f'CREATE INDEX {D["fact"]}_at_idx ON "{D["fact"]}" ({D["f_at"]})')
        lab.sql(f'ANALYZE "{D["fact"]}"')
    return D, spec.format(**D), D[role]


def fast(lab, sset, value, expect_rows=None):
    D, slow, table = prepare(lab, sset)
    want = lab.rows(slow, {"v": value})
    if expect_rows is not None:
        assert len(want) == expect_rows, "тест некоректний: неочікувана кількість рядків у вихідного запиту"
    first = scans(lab.plan(slow, {"v": value}))
    assert [n["Node Type"] for n in first] == ["Seq Scan"], "вихідний запит до змін має читати таблицю послідовно (Seq Scan)"
    result = api(8, sset).call("fix")
    assert isinstance(result, (tuple, list)) and len(result) == 2, "fix() має повертати пару (список команд CREATE INDEX, текст запиту)"
    ddl, text = result
    assert isinstance(ddl, (list, tuple)), "перший елемент пари це список команд CREATE INDEX (можливо порожній)"
    assert isinstance(text, str) and "%(v)s" in text, "другий елемент пари це текст запиту з параметром %(v)s"
    if ddl:
        lab.apply_ddl(list(ddl), limit=2)
    lab.sql(f'ANALYZE "{table}"')
    plan = lab.plan(text, {"v": value})
    nodes = [n for n in scans(plan) if n.get("Relation Name") == table]
    assert len(nodes) == 1 and nodes[0]["Node Type"] in ("Index Scan", "Bitmap Heap Scan"), \
        f"очікувалось читання таблиці за індексом, а план такий: {describe(plan)}"
    got = lab.rows(text, {"v": value})
    same_rows(got, want, what="результат пришвидшеного запиту")
    return got


@T08.case("S1", public=True)
def lower_email_existing_s1(lab):
    got = fast(lab, 1, "USER777@example.com", expect_rows=1)
    assert got == [(777,)]


@T08.case("S1", public=True)
def lower_email_other_case_s1(lab):
    fast(lab, 1, "user5@EXAMPLE.com", expect_rows=1)


@T08.case("S2", public=True)
def one_day_s2(lab):
    fast(lab, 2, "2024-05-14")


@T08.case("S2", public=True)
def first_day_s2(lab):
    fast(lab, 2, "2024-03-01")


@T08.case("S3", public=True)
def sku_existing_s3(lab):
    fast(lab, 3, "SKU-0420")


@T08.case("S3", public=True)
def sku_other_s3(lab):
    fast(lab, 3, "SKU-1999")


@pytest.mark.parametrize("sset,case_fn", T08.params(), ids=T08.ids("T08"))
def test_task_08(lab, sset, case_fn):
    case_fn(lab)
