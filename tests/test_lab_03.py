"""Відкриті тести задачі 3: Дублікати осіб і запис, що залишається.

Запуск: pytest tests/test_lab_03.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_03.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from collections import defaultdict
from domains import SETS
from labtools import Cases, add_line, add_person, api, run_select, same_rows

T03 = Cases()


def expected(lab, sset):
    D = SETS[sset]
    people = lab.rows(f'SELECT "{D["p_id"]}", "{D["p_email"]}", "{D["p_city"]}", "{D["p_since"]}" FROM "{D["person"]}"')
    if sset == 2:
        counts = dict(lab.rows(f'SELECT "{D["f_person"]}", count(*) FROM "{D["fact"]}" GROUP BY 1'))
    else:
        counts = dict(lab.rows(f'SELECT "{D["f_person"]}", count(*) FROM "{D["fact"]}" WHERE "{D["f_status"]}" = %s GROUP BY 1', (D["done"],)))
    groups = defaultdict(list)
    for pid, email, city, since in people:
        key = (email or "").strip(" ").lower()
        if not key:
            continue
        groups[(key, city) if sset == 2 else key].append((pid, since))
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        if sset == 3:
            order = sorted(members, key=lambda m: (m[1], m[0]), reverse=True)
        else:
            order = sorted(members, key=lambda m: (-counts.get(m[0], 0), m[0]))
        keeper = order[0][0]
        out += [(m[0], keeper) for m in order[1:]]
    return sorted(out)


def check(lab, sset):
    cols, rows = run_select(lab, api(3, sset).call("query"))
    assert cols == 2, f"у результаті мають бути 2 стовпці (запис-дублікат, запис, що залишається), отримано {cols}"
    same_rows(rows, expected(lab, sset), what="пари дублікатів")
    return rows


def seed(lab, sset, *roles):
    return lab.use(sset, *(roles or ("person", "fact")))


def full_report(lab, sset):
    seed(lab, sset)
    rows = check(lab, sset)
    assert len(rows) == 45, f"у даних набору 45 записів-дублікатів, у результаті {len(rows)}"


@T03.case("S1", public=True)
def full_data_s1(lab):
    full_report(lab, 1)


@T03.case("S2", public=True)
def full_data_s2(lab):
    full_report(lab, 2)


@T03.case("S3", public=True)
def full_data_s3(lab):
    full_report(lab, 3)


@T03.case("S1", public=True)
def more_orders_wins_s1(lab):
    D = seed(lab, 1)
    add_person(lab, D, 800001, "Ivan@Test.com")
    add_person(lab, D, 800002, " ivan@test.com")
    add_line(lab, D, 900001, 800002, 1, 100, "2035-01-01 10:00")
    add_line(lab, D, 900002, 800001, 1, 100, "2035-01-02 10:00", status=D["bad"])
    rows = check(lab, 1)
    assert (800001, 800002) in rows, "залишається запис із більшою кількістю виконаних подій; скасовані не рахуються"


@T03.case("S2", public=True)
def different_city_is_not_duplicate_s2(lab):
    D = seed(lab, 2)
    add_person(lab, D, 800001, "anna@test.com", city="Львів")
    add_person(lab, D, 800002, "ANNA@test.com", city="Одеса")
    add_person(lab, D, 800003, "anna@test.com ", city="Львів")
    rows = check(lab, 2)
    assert (800003, 800001) in rows and not any(r[0] == 800002 or r[1] == 800002 for r in rows), "різні міста не є дублікатами"


@T03.case("S3", public=True)
def latest_registration_wins_s3(lab):
    D = seed(lab, 3)
    add_person(lab, D, 800001, "olga@test.com", since="2024-01-01")
    add_person(lab, D, 800002, "OLGA@test.com", since="2025-01-01")
    add_person(lab, D, 800003, "olga@test.com", since="2025-01-01")
    rows = check(lab, 3)
    assert (800001, 800003) in rows and (800002, 800003) in rows, "залишається найпізніша реєстрація, за рівних дат запис із більшим ідентифікатором"


@pytest.mark.parametrize("sset,case_fn", T03.params(), ids=T03.ids("T03"))
def test_task_03(lab, sset, case_fn):
    case_fn(lab)
