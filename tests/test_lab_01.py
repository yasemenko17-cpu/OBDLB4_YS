"""Відкриті тести задачі 1: Квартальний рейтинг груп позицій.

Запуск: pytest tests/test_lab_01.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_01.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from domains import SETS
from labtools import Cases, add_item, add_line, api, run_select, same_rows

T01 = Cases()

EXTRA = {1: "TRUE", 2: "f.{amount} >= 200", 3: "f.{qty} >= 2 AND f.{at} >= '2024-04-01'"}


def extra(D, sset):
    return EXTRA[sset].format(amount=D["f_amount"], qty=D["f_qty"], at=D["f_at"])


def expected(lab, sset):
    """Незалежне обчислення звіту в Python за сирими рядками."""
    D = SETS[sset]
    lines = lab.rows(
        f'SELECT f."{D["f_at"]}", i."{D["i_kind"]}", i."{D["i_id"]}", i."{D["i_code"]}", f."{D["f_person"]}", f."{D["f_amount"]}" '
        f'FROM "{D["fact"]}" f JOIN "{D["item"]}" i ON i."{D["i_id"]}" = f."{D["f_item"]}" '
        f'WHERE f."{D["f_status"]}" = %s AND {extra(D, sset)}', (D["done"],))
    per_item = defaultdict(Decimal)
    per_kind = defaultdict(Decimal)
    buyers = defaultdict(set)
    for at, kind, item_id, code, person, amount in lines:
        q = f"{at.year}-Q{(at.month - 1) // 3 + 1}"
        per_item[(q, kind, item_id, code)] += amount
        per_kind[(q, kind)] += amount
        buyers[(q, kind)].add(person)
    top = {}
    for (q, kind, item_id, code), rev in per_item.items():
        cur = top.get((q, kind))
        if cur is None or (rev, -item_id) > (cur[0], -cur[1]):
            top[(q, kind)] = (rev, item_id, code)
    total = defaultdict(Decimal)
    for (q, kind), rev in per_kind.items():
        total[q] += rev
    prev = {}
    out = []
    for (q, kind) in sorted(per_kind):
        rev = per_kind[(q, kind)]
        share = (100 * rev / total[q]).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        position = 1 + sum(1 for (q2, k2), r2 in per_kind.items() if q2 == q and r2 > rev)
        delta = rev - prev[kind] if kind in prev else None
        prev[kind] = rev
        out.append((q, kind, rev, len(buyers[(q, kind)]), top[(q, kind)][2], share, position, delta))
    out.sort(key=lambda r: (r[0], r[6], r[1]))
    return out


def check(lab, sset, text=None, what="звіт"):
    text = text or api(1, sset).call("query")
    cols, rows = run_select(lab, text)
    assert cols == 8, f"у звіті має бути 8 стовпців (квартал, група, виручка, покупці, позиція-лідер, частка, місце, зміна), отримано {cols}"
    same_rows(rows, expected(lab, sset), what=what)
    return rows


def full_report(lab, sset):
    lab.use(sset, "item", "fact")
    rows = check(lab, sset)
    assert len(rows) >= 20, "очікувалось щонайменше 20 рядків звіту на повних даних"


@T01.case("S1", public=True)
def full_data_s1(lab):
    full_report(lab, 1)


@T01.case("S2", public=True)
def full_data_s2(lab):
    full_report(lab, 2)


@T01.case("S3", public=True)
def full_data_s3(lab):
    full_report(lab, 3)


def new_period(lab, sset, base_id=900000):
    D = SETS[sset]
    lab.use(sset, "item", "fact")
    return D


def lines_two_kinds(lab, D):
    add_item(lab, D, 9001, "ZZ-1", "Тестова-А")
    add_item(lab, D, 9002, "ZZ-2", "Тестова-А")
    add_item(lab, D, 9003, "ZZ-3", "Тестова-Б")


@T01.case("S1", public=True)
def tie_and_buyers_s1(lab):
    D = new_period(lab, 1)
    lines_two_kinds(lab, D)
    # рівна виручка груп: однакове місце; один покупець двічі: покупців рахуємо різних
    add_line(lab, D, 900001, 1, 9001, 300, "2030-02-01 10:00")
    add_line(lab, D, 900002, 1, 9002, 300, "2030-02-02 10:00")
    add_line(lab, D, 900003, 2, 9003, 600, "2030-02-03 10:00")
    rows = check(lab, 1)
    mine = [r for r in rows if r[0] == "2030-Q1"]
    assert [(r[1], r[3], r[6]) for r in mine] == [("Тестова-А", 1, 1), ("Тестова-Б", 1, 1)], "рівна виручка має давати однакове місце (rank), а покупців слід рахувати різних"


@T01.case("S2", public=True)
def tie_inside_group_s2(lab):
    D = new_period(lab, 2)
    lines_two_kinds(lab, D)
    # у групі дві позиції з однаковою виручкою: лідер має найменший ідентифікатор
    add_line(lab, D, 900001, 5, 9002, 400, "2030-05-01 10:00")
    add_line(lab, D, 900002, 6, 9001, 400, "2030-05-02 10:00")
    rows = check(lab, 2)
    assert [r[4] for r in rows if r[0] == "2030-Q2" and r[1] == "Тестова-А"] == ["ZZ-1"]


@T01.case("S3", public=True)
def only_cancelled_not_in_report_s3(lab):
    D = new_period(lab, 3)
    lines_two_kinds(lab, D)
    add_line(lab, D, 900001, 5, 9001, 500, "2030-08-01 10:00", status=D["bad"])
    add_line(lab, D, 900002, 6, 9002, 500, "2030-08-02 10:00", status=D["open"])
    rows = check(lab, 3)
    assert all(r[0] != "2030-Q3" for r in rows), "квартал, де немає виконаних подій, не повинен потрапляти до звіту"


@pytest.mark.parametrize("sset,case_fn", T01.params(), ids=T01.ids("T01"))
def test_task_01(lab, sset, case_fn):
    case_fn(lab)
