"""Ручний запуск вашої задачі на даних вашого набору з виводом планів: python try_it.py <номер задачі 1-10>

Скрипт створює тимчасову схему try_it_<токен>, копіює в неї таблиці вашого набору (набір визначає VARIANT у вашому файлі),
виконує вашу функцію і друкує результат. Для задач 5-9 показано план запиту (звичайний текстовий EXPLAIN) до створення
індексів і після нього, для задачі 8 також ваш запит. Схема видаляється після завершення.
Потрібен запущений PostgreSQL: змінні PGHOST, PGPORT, PGUSER, PGPASSWORD (у Codespaces вони вже задані).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))

from conftest import load  # noqa: E402
from dbtools import Lab  # noqa: E402
from domains import SETS  # noqa: E402

QUERIES = {
    5: {1: ("SELECT id, {f_amount} FROM {fact} WHERE {f_person} = 57 AND {f_at} >= '2024-05-01' AND {f_at} < '2024-06-01' ORDER BY {f_at}", 1),
        2: ("SELECT id, {f_at} FROM {fact} WHERE {f_person} = 57 AND {f_status} = '{done}' ORDER BY {f_at} DESC LIMIT 10", 1),
        3: ("SELECT id, {f_amount} FROM {fact} WHERE {f_person} = 57 AND {f_status} = '{done}' AND {f_at} >= '2024-06-01' ORDER BY {f_at}", 1)},
    6: {1: ("SELECT id, {f_person}, {f_amount} FROM {fact} WHERE {f_status} = '{open}' AND {f_at} < '2024-03-01' ORDER BY {f_at}", 1),
        2: ("SELECT id, {f_item} FROM {fact} WHERE {f_status} = '{open}' AND {f_person} = 57", 1),
        3: ("SELECT id, {f_item} FROM {fact} WHERE {f_status} = '{open}' AND {f_at} >= '2024-09-01' ORDER BY {f_at} LIMIT 50", 1)},
    7: {1: ("SELECT {f_item}, {f_qty} FROM {fact} WHERE {f_person} = 57", 1),
        2: ("SELECT {f_amount} FROM {fact} WHERE {f_person} = 57 AND {f_at} >= '2024-05-01'", 1),
        3: ("SELECT {f_at}, {f_amount} FROM {fact} WHERE {f_person} = 57 ORDER BY {f_at}", 1)},
    9: {1: ("SELECT id FROM {fact} WHERE {f_tags} @> ARRAY['vip'] ORDER BY id", 1),
        2: ("SELECT id FROM {fact} WHERE {f_attrs} @> '{{\"channel\": \"web\", \"gift\": true}}' ORDER BY id", 1),
        3: ("SELECT id FROM {fact} WHERE to_tsvector('simple', {f_memo}) @@ to_tsquery('simple', 'гарантія') ORDER BY id", 1)},
}


def show_plan(lab, text, title):
    print(f"\n--- {title}")
    for (line,) in lab.rows("EXPLAIN " + text):
        print("   ", line)


def main(number):
    module = load(number)
    variant = getattr(module, "VARIANT", 0)
    if not variant:
        sys.exit(f"У файлі variants/lab_{number:02d}.py не задано VARIANT")
    sset = (variant - 1) % 3 + 1
    print(f"Задача {number}, варіант {variant}, набір {sset} ({SETS[sset]['title']})")
    with Lab() as lab:
        D = lab.use(sset)
        if number in (1, 2, 3):
            rows = lab.rows(module.query())
            print(f"Рядків у результаті: {len(rows)}; перші 12:")
            for row in rows[:12]:
                print("   ", row)
            show_plan(lab, module.query(), "план вашого запиту")
        elif number == 4:
            for text in (f'SELECT * FROM "{D["fact"]}" WHERE id = 5', f'SELECT * FROM "{D["fact"]}"'):
                plan = lab.raw_plan(text, analyze=True)
                print(f"\nЗапит: {text}\nПідсумок: {module.summarize_plan(plan)}")
        elif number == 8:
            ddl, text = module.fix()
            print("Команди:", ddl)
            print("Запит:", text)
            value = {1: "USER777@example.com", 2: "2024-05-14", 3: "SKU-0420"}[sset]
            if sset == 2:
                lab.sql(f'CREATE INDEX {D["fact"]}_at_idx ON "{D["fact"]}" ({D["f_at"]})')
            show_plan(lab, text.replace("%(v)s", "'" + value + "'"), "план до створення індексів")
            for command in ddl:
                lab.sql(command)
            lab.sql("ANALYZE")
            show_plan(lab, text.replace("%(v)s", "'" + value + "'"), "план після створення індексів")
            print("Знайдено рядків:", len(lab.rows(text, {"v": value})))
        elif number == 10:
            import psycopg
            lab.sql('CREATE TABLE ev (id integer PRIMARY KEY, kind text NOT NULL) WITH (autovacuum_enabled = false)')
            lab.sql("INSERT INTO ev SELECT g, CASE WHEN g % 100 < 90 THEN 'common' WHEN g % 100 < 99 THEN 'seldom' ELSE 'rare' END "
                    "FROM generate_series(1, 100000) AS g")
            lab.sql("CREATE INDEX ON ev (kind)")
            conn = lab.new_connection()
            conn.autocommit = False
            print(module.analyze_effect(conn, "ev", "kind", "common"))
        else:
            text = QUERIES[number][sset][0].format(**D)
            show_plan(lab, text, "план до створення індексів")
            commands = module.indexes()
            print("\nКоманди:", *commands, sep="\n    ")
            for command in commands:
                lab.sql(command)
            lab.sql("VACUUM (ANALYZE) " + D["fact"])
            show_plan(lab, text, "план після створення індексів")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit() or not 1 <= int(sys.argv[1]) <= 10:
        sys.exit(__doc__)
    main(int(sys.argv[1]))
