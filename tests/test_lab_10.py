"""Відкриті тести задачі 10: Вплив ANALYZE: оцінка проти факту.

Запуск: pytest tests/test_lab_10.py            (усі відкриті випадки вашого набору)
        pytest tests/test_lab_10.py -k S2     (лише набір 2; замініть на свій)
Тут лише частина випадків кожного набору; повний набір перевірок є у викладача.
"""
import pytest
from labtools import Cases, api

T10 = Cases()


def make_table(lab, name, column="kind", values=("common", "seldom", "rare")):
    lab.sql(f'CREATE TABLE "{name}" (id integer PRIMARY KEY, "{column}" text NOT NULL, note text) WITH (autovacuum_enabled = false)')
    lab.sql(
        f'INSERT INTO "{name}" SELECT g, CASE WHEN g %% 100 < 90 THEN %s WHEN g %% 100 < 99 THEN %s ELSE %s END, \'x\' '
        "FROM generate_series(1, 100000) AS g", values)
    lab.sql(f'CREATE INDEX ON "{name}" ("{column}")')


def summary(node):
    estimate, actual = node["Plan Rows"], round(node["Actual Rows"])
    return {"node": node["Node Type"], "plan_rows": estimate, "actual_rows": actual,
            "misestimate": round(max(estimate, actual, 1) / max(min(estimate, actual), 1), 2)}


def measure(lab, name, column, value):
    """Те саме, що має робити функція студента, на іншій копії таблиці."""
    text = f'SELECT * FROM "{name}" WHERE "{column}" = %s'
    before = summary(lab.plan(text, (value,), analyze=True)["Plan"])
    lab.sql(f'ANALYZE "{name}"')
    after = summary(lab.plan(text, (value,), analyze=True)["Plan"])
    return {"before": before, "after": after}


def stats_rows(lab, name):
    return lab.value("SELECT count(*) FROM pg_stats WHERE schemaname = %s AND tablename = %s", (lab.schema, name))


def run(lab, sset, value, name="events_a", column="kind", values=("common", "seldom", "rare")):
    make_table(lab, name, column, values)
    make_table(lab, "events_b", column, values)
    want = measure(lab, "events_b", column, value)
    assert stats_rows(lab, name) == 0, "тест некоректний: таблиця вже має статистику"
    got = api(10, sset).call("analyze_effect", lab.new_connection(), name, column, value)
    assert isinstance(got, dict) and set(got) == {"before", "after"}, "функція має повертати словник з ключами before та after"
    for part in ("before", "after"):
        assert isinstance(got[part], dict) and set(got[part]) == {"node", "plan_rows", "actual_rows", "misestimate"}, \
            f"{part}: ключі словника мають бути node, plan_rows, actual_rows, misestimate"
        assert got[part]["node"] == want[part]["node"], f"{part}: вузол {got[part]['node']}, очікувався {want[part]['node']}"
        assert got[part]["plan_rows"] == want[part]["plan_rows"], f"{part}: plan_rows {got[part]['plan_rows']}, очікувалось {want[part]['plan_rows']}"
        assert got[part]["actual_rows"] == want[part]["actual_rows"], f"{part}: actual_rows {got[part]['actual_rows']}, очікувалось {want[part]['actual_rows']}"
        assert got[part]["misestimate"] == pytest.approx(want[part]["misestimate"], abs=0.011), \
            f"{part}: misestimate {got[part]['misestimate']}, очікувалось {want[part]['misestimate']}"
    assert stats_rows(lab, name) > 0, "після функції таблиця має статистику: виконайте ANALYZE цієї таблиці"
    return got, want


@T10.case("S1", public=True)
def common_value_switches_to_seq_scan(lab):
    got, _ = run(lab, 1, "common")
    assert got["before"]["node"] != "Seq Scan" and got["after"]["node"] == "Seq Scan"
    assert got["after"]["misestimate"] < 1.05 < got["before"]["misestimate"]


@T10.case("S1", public=True)
def statistics_appear_only_for_that_table(lab):
    make_table(lab, "other", "kind")
    run(lab, 1, "common")
    assert stats_rows(lab, "other") == 0, "ANALYZE слід виконувати лише для вказаної таблиці"


@T10.case("S2", public=True)
def rare_value_gets_exact_estimate(lab):
    got, _ = run(lab, 2, "rare")
    assert got["before"]["plan_rows"] != got["after"]["plan_rows"] == got["after"]["actual_rows"] == 1000
    assert got["before"]["misestimate"] > 4


@T10.case("S2", public=True)
def misestimate_shrinks(lab):
    got, _ = run(lab, 2, "seldom")
    assert got["after"]["misestimate"] < got["before"]["misestimate"]


@T10.case("S3", public=True)
def middle_value_s3(lab):
    got, _ = run(lab, 3, "seldom")
    assert got["after"]["plan_rows"] == got["after"]["actual_rows"] == 9000


@T10.case("S3", public=True)
def node_types_s3(lab):
    got, _ = run(lab, 3, "common")
    assert got["before"]["node"] in ("Index Scan", "Bitmap Heap Scan")


@pytest.mark.parametrize("sset,case_fn", T10.params(), ids=T10.ids("T10"))
def test_task_10(lab, sset, case_fn):
    case_fn(lab)
