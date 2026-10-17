"""Відкриті тести задачі 9: GIN для масивів, jsonb і тексту.

Запуск: pytest tests/test_lab_09.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_09.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from dbtools import describe, scans, used_indexes
from labtools import Cases, api, same_rows

T09 = Cases()

QUERY = {
    1: "SELECT id FROM {fact} WHERE {f_tags} @> %(v)s::text[] ORDER BY id",
    2: "SELECT id FROM {fact} WHERE {f_attrs} @> %(v)s::jsonb ORDER BY id",
    3: "SELECT id FROM {fact} WHERE to_tsvector('simple', {f_memo}) @@ to_tsquery('simple', %(v)s) ORDER BY id",
}


def gin(lab, sset, value, min_rows=0):
    D = lab.use(sset, "fact")
    text = QUERY[sset].format(**D)
    want = lab.rows(text, {"v": value})
    assert len(want) >= min_rows, "тест некоректний: замало рядків у вихідного запиту"
    assert [n["Node Type"] for n in scans(lab.plan(text, {"v": value}))] == ["Seq Scan"], "до створення індексу план має бути Seq Scan"
    new = lab.apply_ddl(api(9, sset).call("indexes"), limit=1)
    assert len(new) == 1, "потрібен один індекс"
    lab.sql(f'ANALYZE "{D["fact"]}"')
    method = lab.indexes()[new[0]][1]
    assert method == "gin", f"індекс {new[0]} має метод {method}: для операторів @> та @@ потрібен USING gin"
    plan = lab.plan(text, {"v": value})
    nodes = scans(plan)
    assert len(nodes) == 1 and nodes[0]["Node Type"] == "Bitmap Heap Scan", f"очікувався Bitmap Heap Scan, а план такий: {describe(plan)}"
    assert used_indexes(plan) == [new[0]], f"запит використав {used_indexes(plan)}, а не індекс {new[0]}"
    same_rows(lab.rows(text, {"v": value}), want, what="результат після створення індексу")
    return want


@T09.case("S1", public=True)
def rare_tag_s1(lab):
    got = gin(lab, 1, ["vip"], min_rows=50)
    assert len(got) == 80


@T09.case("S1", public=True)
def two_tags_s1(lab):
    gin(lab, 1, ["vip", "gift"])


@T09.case("S2", public=True)
def channel_and_gift_s2(lab):
    gin(lab, 2, '{"channel": "web", "gift": true}', min_rows=10)


@T09.case("S2", public=True)
def gift_only_s2(lab):
    gin(lab, 2, '{"gift": true}', min_rows=50)


@T09.case("S3", public=True)
def rare_word_s3(lab):
    got = gin(lab, 3, "гарантія", min_rows=30)
    assert len(got) == 44


@T09.case("S3", public=True)
def two_words_s3(lab):
    gin(lab, 3, "гарантія & партія")


@pytest.mark.parametrize("sset,case_fn", T09.params(), ids=T09.ids("T09"))
def test_task_09(lab, sset, case_fn):
    case_fn(lab)
