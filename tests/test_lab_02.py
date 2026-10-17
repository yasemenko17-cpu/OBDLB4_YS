"""Відкриті тести задачі 2: Когорти утримання.

Запуск: pytest tests/test_lab_02.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_02.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from domains import SETS
from labtools import Cases, add_line, api, run_select, same_rows

T02 = Cases()

EXTRA = {1: "TRUE", 2: "f.{amount} >= 300", 3: "f.{qty} >= 2"}


def extra(D, sset):
    return EXTRA[sset].format(amount=D["f_amount"], qty=D["f_qty"])


def month_index(ts):
    return ts.year * 12 + ts.month - 1


def expected(lab, sset):
    D = SETS[sset]
    lines = lab.rows(
        f'SELECT f."{D["f_person"]}", f."{D["f_at"]}" FROM "{D["fact"]}" f '
        f'WHERE f."{D["f_status"]}" = %s AND {extra(D, sset)}', (D["done"],))
    months = defaultdict(set)
    for person, at in lines:
        months[person].add(month_index(at))
    cohorts = defaultdict(lambda: [0, 0, 0, 0])
    for person, ms in months.items():
        first = min(ms)
        for off in range(4):
            if first + off in ms:
                cohorts[first][off] += 1
    out = []
    for first in sorted(cohorts):
        m = cohorts[first]
        ret = (Decimal(100) * m[1] / m[0]).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        out.append((f"{first // 12}-{first % 12 + 1:02d}", m[0], m[1], m[2], m[3], ret))
    return out


def check(lab, sset):
    cols, rows = run_select(lab, api(2, sset).call("query"))
    assert cols == 6, f"у звіті має бути 6 стовпців (когорта, m0, m1, m2, m3, утримання за місяць 1), отримано {cols}"
    same_rows(rows, expected(lab, sset), what="звіт когорт")
    return rows


def full_report(lab, sset):
    lab.use(sset, "fact")
    rows = check(lab, sset)
    assert len(rows) >= 8, "очікувалось щонайменше 8 когорт на повних даних"


@T02.case("S1", public=True)
def full_data_s1(lab):
    full_report(lab, 1)


@T02.case("S2", public=True)
def full_data_s2(lab):
    full_report(lab, 2)


@T02.case("S3", public=True)
def full_data_s3(lab):
    full_report(lab, 3)


def seed(lab, sset):
    D = SETS[sset]
    lab.use(sset, "fact")
    return D


@T02.case("S1", public=True)
def new_cohort_counts_s1(lab):
    D = seed(lab, 1)
    # три особи з першою подією у січні 2035: m1, m2, m3 рахують різних осіб, а не події
    add_line(lab, D, 900001, 700001, 1, 300, "2035-01-05 10:00")
    add_line(lab, D, 900002, 700001, 1, 300, "2035-02-05 10:00")
    add_line(lab, D, 900003, 700001, 1, 300, "2035-02-25 10:00")
    add_line(lab, D, 900004, 700002, 1, 300, "2035-01-20 10:00")
    add_line(lab, D, 900005, 700003, 1, 300, "2035-01-07 10:00")
    add_line(lab, D, 900006, 700003, 1, 300, "2035-03-07 10:00")
    add_line(lab, D, 900007, 700003, 1, 300, "2035-04-07 10:00")
    rows = check(lab, 1)
    assert [r for r in rows if r[0] == "2035-01"] == [("2035-01", 3, 1, 1, 1, Decimal("33.3"))]


@T02.case("S2", public=True)
def first_event_defines_cohort_s2(lab):
    D = seed(lab, 2)
    # особа з подіями у січні й лютому належить до січневої когорти; пізніші події не створюють нової когорти
    add_line(lab, D, 900001, 700001, 1, 300, "2035-01-31 23:00")
    add_line(lab, D, 900002, 700001, 1, 300, "2035-02-01 00:00")
    rows = check(lab, 2)
    assert [r[:3] for r in rows if r[0] >= "2035-01"] == [("2035-01", 1, 1)]


@T02.case("S3", public=True)
def non_done_do_not_count_s3(lab):
    D = seed(lab, 3)
    add_line(lab, D, 900001, 700001, 1, 300, "2035-01-10 10:00", status=D["bad"])
    add_line(lab, D, 900002, 700001, 1, 300, "2035-02-10 10:00")
    rows = check(lab, 3)
    assert [r[:3] for r in rows if r[0] >= "2035-01"] == [("2035-02", 1, 0)], "скасовані події не визначають когорту"


@pytest.mark.parametrize("sset,case_fn", T02.params(), ids=T02.ids("T02"))
def test_task_02(lab, sset, case_fn):
    case_fn(lab)
