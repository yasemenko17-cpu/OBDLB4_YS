"""Перевірник наскрізного проєкту (частина Б, аналітичні запити й індекси): розгортання, масштабування даних, плани до і після.

Запуск:  python project_check/check_project.py [тека_проєкту]   або   pytest project_check
Тека проєкту за замовчуванням: project/ (поруч із цим файлом на рівень вище). Змінна PROJECT_DIR задає іншу теку.
Потрібен PostgreSQL (змінні PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE). Перевірник працює в тимчасовій
схемі, яку видаляє. Кожне зауваження має код (MIG03, LOAD05, POST02, AN03, GIT06 тощо) і пояснення.
Перевірник відповідає на питання «чи розгортається проєкт, чи запити коректні на великих даних і чи індекси справді
змінили плани двох запитів»; змістову якість запитів і висновків переглядає викладач.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent
MIN_MIGRATIONS = 3
MIN_TABLES = 6
MIN_ROWS_PER_TABLE = 3
MIN_ROWS_TOTAL = 150
MIN_ROWS_BIG = 50
MIN_COMMITS = 5
MIN_MIGRATION_COMMITS = 3
MIN_ANALYTICS_COMMITS = 2
BIG_ROWS = 50000
SCALE_ROWS = 100000
QUERY_COUNT = (5, 6)
REPORT_SECTIONS = ("Запити", "План до і після", "Висновок")
CONCLUSION_MIN_WORDS = 30
PLANNER = ("jit = off", "max_parallel_workers_per_gather = 0", "default_statistics_target = 1000",
           "random_page_cost = 1.1", "effective_cache_size = '1GB'")
TABLE_SCANS = ("Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan")
PLACEHOLDERS = {"", "—", "-", "...", "ЗАПОВНІТЬ", "TBD"}
MIGRATION_NAME = re.compile(r"V(\d+)__([a-z0-9_]+)\.sql")
COPY_LINE = re.compile(r"""^\\copy\s+(?P<table>"[^"]+"|\w+)\s*(?P<cols>\([^)]*\))?\s+from\s+'(?P<file>[^']+)'\s*(?P<rest>.*?);?\s*$""",
                       re.I)


def _connect():
    cfg = dict(host=os.environ.get("PGHOST", "localhost"), port=int(os.environ.get("PGPORT", "5432")),
               user=os.environ.get("PGUSER", "postgres"), password=os.environ.get("PGPASSWORD", "postgres"),
               dbname=os.environ.get("PGDATABASE", "postgres"))
    conn = psycopg.connect(connect_timeout=5, **cfg)
    conn.autocommit = True
    return conn, cfg


def checksum(text):
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return hashlib.sha256("\n".join(lines).rstrip("\n").encode("utf-8")).hexdigest()[:12]


def _first_line(exc):
    return str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__


# ---------------------------------------------------------------- каталог

_COLUMNS = """
SELECT c.relname::text, a.attname::text, format_type(a.atttypid, a.atttypmod), a.attnotnull, a.attidentity::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = current_schema() AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""
_CONSTRAINTS = """
SELECT rel.relname::text, con.contype::text,
  (SELECT array_agg(att.attname::text ORDER BY k.ord) FROM unnest(con.conkey) WITH ORDINALITY AS k(num, ord)
     JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.num),
  frel.relname::text,
  (SELECT array_agg(att.attname::text ORDER BY k.ord) FROM unnest(con.confkey) WITH ORDINALITY AS k(num, ord)
     JOIN pg_attribute att ON att.attrelid = con.confrelid AND att.attnum = k.num),
  con.convalidated
FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace n ON n.oid = rel.relnamespace LEFT JOIN pg_class frel ON frel.oid = con.confrelid
WHERE n.nspname = current_schema() AND con.contype IN ('p', 'u', 'f', 'c')
"""


def read_catalog(cur):
    """{таблиця: {"columns": [(ім'я, тип, обов'язковий, identity)], "pk": [...], "unique": [...], "fks": [...], "checks": n}}."""
    tables = {}
    cur.execute(_COLUMNS)
    for table, col, typ, notnull, ident in cur.fetchall():
        t = tables.setdefault(table, {"columns": [], "pk": [], "unique": [], "fks": [], "checks": 0})
        t["columns"].append((col, typ, notnull, ident != ""))
    cur.execute(_CONSTRAINTS)
    for table, kind, cols, ftable, fcols, valid in cur.fetchall():
        t = tables[table]
        if kind == "p":
            t["pk"] = list(cols)
        elif kind == "u":
            t["unique"].append(list(cols))
        elif kind == "f":
            t["fks"].append({"columns": list(cols), "ref_table": ftable, "ref_columns": list(fcols), "valid": valid})
        else:
            t["checks"] += 1
    return tables


def _q(name):
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def scratch(prefix="proj"):
    """Тимчасова схема з search_path; повертає (курсор, назва схеми); після виходу схема видаляється."""
    conn, _ = _connect()
    name = f"{prefix}_{uuid.uuid4().hex[:10]}"
    cur = conn.cursor()
    try:
        cur.execute(f'CREATE SCHEMA "{name}"')
        cur.execute(f'SET search_path = "{name}"')
        yield cur, name
    finally:
        try:
            cur.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            pass
        try:
            cur.execute("SET search_path = public")
            cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        finally:
            conn.close()


# ---------------------------------------------------------------- міграції


def list_migrations(project):
    """[(версія, ім'я файлу, текст)] за зростанням версії і зауваження за іменами."""
    folder = project / "migrations"
    if not folder.is_dir():
        return [], ["MIG00: немає теки migrations/ (файли V001__назва.sql, V002__назва.sql, ...)"]
    out, problems, seen = [], [], {}
    for path in sorted(folder.glob("*.sql")):
        m = MIGRATION_NAME.fullmatch(path.name)
        if not m:
            problems.append(f"MIG01: ім'я файлу {path.name} не відповідає шаблону V<число>__<назва>.sql (малі літери, цифри, підкреслення)")
            continue
        version = int(m.group(1))
        if version in seen:
            problems.append(f"MIG01: версія {version} повторюється у файлах {seen[version]} і {path.name}")
            continue
        seen[version] = path.name
        out.append((version, path.name, path.read_text(encoding="utf-8")))
    out.sort()
    if len(out) < MIN_MIGRATIONS:
        problems.append(f"MIG02: міграцій {len(out)}, потрібно щонайменше {MIN_MIGRATIONS} (початкова схема і ще дві зміни)")
    return out, problems


def apply_all(cur, migrations):
    """Застосовує міграції по одній у транзакції й записує їх у schema_migrations. Повертає (кількість, зауваження)."""
    cur.execute("CREATE TABLE schema_migrations (version integer PRIMARY KEY, name text NOT NULL, checksum text NOT NULL, "
                "applied_at timestamptz NOT NULL DEFAULT now())")
    done = 0
    for version, name, sql in migrations:
        cur.execute("BEGIN")
        try:
            cur.execute(sql)
            cur.execute("INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)", (version, name, checksum(sql)))
            cur.execute("COMMIT")
        except psycopg.Error as exc:
            cur.execute("ROLLBACK")
            return done, [f"MIG03: міграція {name} відхилена сервером: {_first_line(exc)}"]
        done += 1
    return done, []


def check_migrations(project, cur):
    migrations, problems = list_migrations(project)
    if not migrations:
        return None, problems
    done, errs = apply_all(cur, migrations)
    problems += errs
    if errs:
        return None, problems
    catalog = {t: v for t, v in read_catalog(cur).items() if t != "schema_migrations"}
    first = migrations[0][2]
    if len(re.findall(r"create\s+table", first, re.I)) < MIN_TABLES:
        problems.append(f"MIG04: у першій міграції {migrations[0][1]} менше {MIN_TABLES} команд CREATE TABLE "
                        "(вона має містити схему з LAB01)")
    later = " ".join(m[2] for m in migrations[1:])
    if not re.search(r"\balter\s+table\b|\bcreate\s+(unique\s+)?index\b", later, re.I):
        problems.append("MIG05: пізніші міграції не містять жодної команди ALTER TABLE або CREATE INDEX (міграція має змінювати структуру)")
    if len(catalog) < MIN_TABLES:
        problems.append(f"MIG06: після міграцій у схемі {len(catalog)} таблиць, потрібно щонайменше {MIN_TABLES}")
    for name, t in sorted(catalog.items()):
        if not t["pk"]:
            problems.append(f"MIG07: таблиця {name} не має первинного ключа")
    cur.execute("SELECT count(*) FROM schema_migrations")
    if cur.fetchone()[0] != len(migrations):
        problems.append("MIG08: журнал schema_migrations не збігається з кількістю міграцій")
    return catalog, problems


# ---------------------------------------------------------------- завантаження даних


def parse_load(project):
    """[(номер рядка, таблиця, список стовпців або None, файл, решта параметрів)] і зауваження."""
    path = project / "load.psql"
    if not path.exists():
        return [], ["LOAD00: немає файлу load.psql (команди \\copy у порядку завантаження)"]
    out, problems = [], []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("--") or line.startswith("\\set") or line.startswith("\\echo"):
            continue
        m = COPY_LINE.match(line)
        if not m:
            problems.append(f"LOAD01: load.psql, рядок {number}: очікується \\copy таблиця [(стовпці)] FROM 'файл' WITH (FORMAT csv, HEADER true)")
            continue
        table = m.group("table").strip('"')
        out.append((number, table, m.group("cols"), m.group("file"), m.group("rest") or "WITH (FORMAT csv, HEADER true)"))
    return out, problems


def run_load(project, cur, catalog):
    commands, problems = parse_load(project)
    loaded = {}
    for number, table, cols, file, rest in commands:
        if table not in catalog:
            problems.append(f"LOAD02: load.psql, рядок {number}: таблиці {table} немає у схемі")
            continue
        path = (project / file)
        if not path.is_file():
            problems.append(f"LOAD03: load.psql, рядок {number}: немає файлу {file}")
            continue
        if table in loaded:
            problems.append(f"LOAD04: таблицю {table} завантажено двічі (рядок {number})")
            continue
        sql = f"COPY {_q(table)} {cols or ''} FROM STDIN {rest}"
        try:
            with cur.copy(sql) as cp:
                cp.write(path.read_bytes())
        except psycopg.Error as exc:
            problems.append(f"LOAD05: load.psql, рядок {number}, таблиця {table}: {_first_line(exc)} "
                            "(перевірте порядок: спершу батьківські таблиці, потім дочірні; і формат CSV)")
            continue
        cur.execute(f"SELECT count(*) FROM {_q(table)}")
        loaded[table] = cur.fetchone()[0]
    for table in sorted(set(catalog) - {name for _, name, *_ in commands}):
        problems.append(f"LOAD06: таблиця {table} не завантажується: у load.psql немає команди \\copy для неї")
    for table, n in sorted(loaded.items()):
        if n < MIN_ROWS_PER_TABLE:
            problems.append(f"LOAD07: у таблиці {table} {n} рядків, потрібно щонайменше {MIN_ROWS_PER_TABLE}")
    if loaded:
        total = sum(loaded.values())
        if total < MIN_ROWS_TOTAL:
            problems.append(f"LOAD08: усього рядків {total}, потрібно щонайменше {MIN_ROWS_TOTAL}")
        if max(loaded.values()) < MIN_ROWS_BIG:
            problems.append(f"LOAD09: немає жодної таблиці з {MIN_ROWS_BIG}+ рядками (згенеруйте дані скриптом make_data.py)")
    if not (project / "make_data.py").exists():
        problems.append("LOAD10: немає скрипта make_data.py, що генерує CSV (дані мають відтворюватися)")
    return loaded, problems


def _sql_body(text):
    return re.sub(r"--[^\n]*", "", text).strip()


def check_post_load(project, cur, catalog):
    path = project / "post_load.sql"
    if not path.exists():
        return ["POST00: немає файлу post_load.sql (вирівнювання послідовностей після завантаження)"]
    text = path.read_text(encoding="utf-8")
    out = []
    if _sql_body(text):
        try:
            cur.execute(text)
        except psycopg.Error as exc:
            return [f"POST01: post_load.sql відхилено сервером: {_first_line(exc)}"]
    for table, t in sorted(catalog.items()):
        for col, _, _, identity in t["columns"]:
            if not identity:
                continue
            cur.execute(f"SELECT max({_q(col)}) FROM {_q(table)}")
            top = cur.fetchone()[0]
            cur.execute("SELECT nextval(pg_get_serial_sequence(%s, %s))", (_q(table), col))
            nxt = cur.fetchone()[0]
            if top is not None and nxt <= top:
                out.append(f"POST02: у {table}.{col} наступне значення послідовності {nxt} не більше за максимум {top} "
                           "(додайте в post_load.sql setval(...))")
    return out




# ---------------------------------------------------------------- аналітика й індекси


def _body(text):
    """Текст SQL без рядкових коментарів і порожніх країв."""
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("--")).strip().rstrip(";").strip()


def _plain(sql):
    """Запит без рядкових літералів і коментарів, малими літерами (для пошуку конструкцій)."""
    return re.sub(r"'(?:[^']|'')*'", "''", _body(sql)).lower()


def _walk(node):
    yield node
    for child in node.get("Plans", []):
        yield from _walk(child)


def _plan(cur, sql):
    cur.execute("EXPLAIN (FORMAT JSON) " + sql)
    return cur.fetchone()[0][0]["Plan"]


def _indexes(cur):
    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()")
    return {r[0] for r in cur.fetchall()}


def _digest(rows):
    return hashlib.md5("\n".join(sorted(repr(tuple(r)) for r in rows)).encode("utf-8")).hexdigest()


def _table_rows(cur, catalog):
    out = {}
    for table in catalog:
        cur.execute(f"SELECT count(*) FROM {_q(table)}")
        out[table] = cur.fetchone()[0]
    return out


def _report_sections(text):
    found = {}
    for m in re.finditer(r"^##\s+(.+?)\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S):
        found[m.group(1).strip()] = m.group(2)
    return found


def check_report(folder, optimized, notes_ok=True):
    out = []
    path = folder / "REPORT.md"
    text = path.read_text(encoding="utf-8")
    sections = _report_sections(text)
    for name in REPORT_SECTIONS:
        if name not in sections:
            out.append(f"AN11: у REPORT.md немає розділу «## {name}»")
    plans = sections.get("План до і після", "")
    for query in optimized:
        m = re.search(rf"^###\s+{re.escape(query)}\b.*?$(.*?)(?=^###\s|\Z)", plans, re.M | re.S)
        if not m:
            out.append(f"AN11: у розділі «План до і після» немає підрозділу «### {query}»")
            continue
        blocks = re.findall(r"```[^\n]*\n(.*?)```", m.group(1), re.S)
        if len(blocks) < 2:
            out.append(f"AN11: у підрозділі {query} потрібні два блоки коду: план до індексу й план після (вставте текст EXPLAIN)")
            continue
        before, after = blocks[0], blocks[1]
        if "Seq Scan" not in before:
            out.append(f"AN11: перший блок {query} (план до) має містити вузол Seq Scan")
        if not re.search(r"Index Scan|Index Only Scan|Bitmap Heap Scan", after):
            out.append(f"AN11: другий блок {query} (план після) має містити Index Scan, Index Only Scan або Bitmap Heap Scan")
        if "rows=" not in before or "rows=" not in after:
            out.append(f"AN11: плани {query} мають бути скопійованими з EXPLAIN (з оцінками rows=...)")
    words = re.findall(r"[\w'’-]+", sections.get("Висновок", ""))
    if len(words) < CONCLUSION_MIN_WORDS or "ЗАПОВНІТЬ" in sections.get("Висновок", ""):
        out.append(f"AN11: розділ «Висновок» порожній або містить заглушку (потрібно щонайменше {CONCLUSION_MIN_WORDS} слів)")
    return out


def check_analytics(project, cur, schema, catalog):
    folder = project / "analytics"
    out = []
    if not folder.is_dir():
        return ["AN00: немає теки analytics/ (scale.sql, q01.sql ... q06.sql, indexes.sql, analytics.json, REPORT.md)"]
    queries = sorted(p for p in folder.glob("q*.sql"))
    for name in ("scale.sql", "indexes.sql", "analytics.json", "REPORT.md"):
        if not (folder / name).is_file():
            out.append(f"AN00: немає файлу analytics/{name}")
    if not QUERY_COUNT[0] <= len(queries) <= QUERY_COUNT[1]:
        out.append(f"AN02: запитів q*.sql {len(queries)}, потрібно від {QUERY_COUNT[0]} до {QUERY_COUNT[1]}")
    if out:
        return out

    # --- масштабування даних
    scale = (folder / "scale.sql").read_text(encoding="utf-8")
    if re.search(r"\brandom\s*\(", _body(scale), re.I):
        out.append("AN01: scale.sql використовує random(): дані мають відтворюватися однаково (виводьте значення з номера рядка арифметикою)")
    if not _body(scale):
        return out + ["AN01: scale.sql порожній"]
    try:
        cur.execute("SET statement_timeout = 180000")
        cur.execute(scale)
    except psycopg.Error as exc:
        return out + [f"AN01: scale.sql відхилено сервером: {_first_line(exc)}"]
    for setting in PLANNER:
        cur.execute("SET " + setting)
    cur.execute("ANALYZE")
    sizes = _table_rows(cur, catalog)
    big = {t: n for t, n in sizes.items() if n >= BIG_ROWS}
    if max(sizes.values()) < SCALE_ROWS:
        out.append(f"AN01: після scale.sql найбільша таблиця має {max(sizes.values())} рядків, потрібно щонайменше {SCALE_ROWS}")

    # --- запити
    meta, before = {}, {}
    cur.execute("SET statement_timeout = 60000")
    bodies = {}
    for path in queries:
        qid = path.stem.split("_")[0]
        raw = path.read_text(encoding="utf-8")
        body = _body(raw)
        bodies[qid] = body
        if not re.search(r"^--\s*title:\s*\S+", raw, re.M | re.I):
            out.append(f"AN02: у {path.name} немає рядка «-- title: короткий опис запиту»")
        if ";" in re.sub(r"'(?:[^']|'')*'", "''", body):
            out.append(f"AN02: у {path.name} має бути рівно один запит без «;» всередині")
            continue
        if not re.match(r"(?is)^(select|with)\b", body):
            out.append(f"AN02: {path.name} має починатися зі SELECT або WITH")
            continue
        try:
            plan = _plan(cur, body)
            cur.execute(body)
            rows = cur.fetchall()
        except psycopg.Error as exc:
            out.append(f"AN04: {path.name}: {_first_line(exc)}")
            continue
        if not rows:
            out.append(f"AN05: {path.name} не повертає жодного рядка на масштабованих даних")
        before[qid] = (plan, _digest(rows))
    plain = [_plain(b) for b in bodies.values()]
    if not any(re.search(r"\bwith\b", p) for p in plain):
        out.append("AN03: жоден запит не використовує CTE (WITH)")
    if not any(re.search(r"\bover\s*\(", p) for p in plain):
        out.append("AN03: жоден запит не використовує віконну функцію (OVER (...))")
    if sum(1 for p in plain if re.search(r"\bjoin\b", p)) < 2:
        out.append("AN03: щонайменше два запити мають з'єднувати таблиці (JOIN)")
    if not any(re.search(r"\bgroup\s+by\b", p) and re.search(r"\b(count|sum|avg|min|max)\s*\(", p) for p in plain):
        out.append("AN03: жоден запит не групує дані з агрегатною функцією (GROUP BY ... count/sum/avg)")
    if len({re.sub(r"\s+", " ", p) for p in plain}) < len(plain):
        out.append("AN02: серед запитів є однакові")

    # --- опис оптимізації
    try:
        meta = json.loads((folder / "analytics.json").read_text(encoding="utf-8"))
    except ValueError as exc:
        return out + [f"AN06: analytics.json не є коректним JSON: {exc}"]
    optimized = meta.get("optimized")
    if (not isinstance(optimized, list) or len(optimized) != 2 or len(set(optimized)) != 2
            or any(q not in bodies for q in optimized)):
        return out + ["AN06: analytics.json: поле optimized має містити назви двох різних прискорених запитів, наприклад [\"q02\", \"q05\"]"]

    # --- індекси
    idx_text = (folder / "indexes.sql").read_text(encoding="utf-8")
    statements = [s.strip() for s in _body(idx_text).split(";") if s.strip()]
    if not statements or any(not re.match(r"(?is)^create\s+(unique\s+)?index\b", s) for s in statements):
        return out + ["AN07: indexes.sql має містити лише команди CREATE INDEX (одну чи кілька, через «;»)"]
    names_before = _indexes(cur)
    try:
        for s in statements:
            cur.execute(s)
        cur.execute("ANALYZE")
    except psycopg.Error as exc:
        return out + [f"AN07: indexes.sql відхилено сервером: {_first_line(exc)}"]
    created = _indexes(cur) - names_before
    if not 1 <= len(created) <= 4:
        out.append(f"AN07: indexes.sql створив {len(created)} індексів, потрібно від 1 до 4 (кожен індекс має ціну)")

    for qid, body in bodies.items():
        if qid not in before:
            continue
        try:
            plan = _plan(cur, body)
            cur.execute(body)
            digest = _digest(cur.fetchall())
        except psycopg.Error as exc:
            out.append(f"AN04: {qid} після створення індексів: {_first_line(exc)}")
            continue
        if digest != before[qid][1]:
            out.append(f"AN10: результат {qid} змінився після створення індексів (якщо в запиті є LIMIT, зробіть ORDER BY однозначним)")
        if qid in optimized:
            old = [n for n in _walk(before[qid][0]) if n["Node Type"] == "Seq Scan" and n.get("Relation Name") in big]
            if not old:
                out.append(f"AN08: у плані {qid} до індексів немає Seq Scan великої таблиці (від {BIG_ROWS} рядків): прискорювати нічого або запит читає замало даних")
            used = {n.get("Index Name") for n in _walk(plan) if n.get("Index Name")}
            new_scan = [n for n in _walk(plan) if n["Node Type"] in TABLE_SCANS[1:] and n.get("Index Name") in created
                        or n["Node Type"] == "Bitmap Index Scan" and n.get("Index Name") in created]
            if not (used & created):
                out.append(f"AN09: план {qid} після створення індексів не використовує жоден із нових індексів ({', '.join(sorted(created))})")
            elif [n for n in _walk(plan) if n["Node Type"] == "Seq Scan" and n.get("Relation Name") in {o.get('Relation Name') for o in old}]:
                out.append(f"AN09: план {qid} усе ще читає велику таблицю послідовно (Seq Scan)")
    out += check_report(folder, optimized)
    return out


# ---------------------------------------------------------------- Git


def _git(project, *args):
    return subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)


def check_git(project):
    try:
        top = _git(project, "rev-parse", "--show-toplevel")
    except FileNotFoundError:
        return ["GIT00: команда git не знайдена"]
    if top.returncode != 0:
        return ["GIT01: теку проєкту не під керуванням Git (виконайте git init, git add, git commit)"]
    out = []
    count = _git(project, "rev-list", "--count", "HEAD")
    n = int(count.stdout.strip() or 0) if count.returncode == 0 else 0
    if n < MIN_COMMITS:
        out.append(f"GIT02: комітів {n}, потрібно щонайменше {MIN_COMMITS} (історія LAB02 і окремі коміти аналітики)")
    tracked = set(_git(project, "ls-files", "--", ".").stdout.split())
    for f in ("load.psql", "post_load.sql", "make_data.py"):
        if f not in tracked:
            out.append(f"GIT03: файл {f} не додано в Git")
    for sub in ("migrations", "data", "analytics"):
        if not any(t.startswith(sub + "/") for t in tracked):
            out.append(f"GIT03: у Git немає жодного файлу з теки {sub}/")
    log = _git(project, "log", "--format=%H", "--", "migrations")
    if len([x for x in log.stdout.split() if x]) < MIN_MIGRATION_COMMITS:
        out.append(f"GIT05: теку migrations/ змінено менш ніж у {MIN_MIGRATION_COMMITS} комітах "
                   "(кожну міграцію фіксуйте окремим комітом)")
    log = _git(project, "log", "--format=%H", "--", "analytics")
    commits = len([x for x in log.stdout.split() if x])
    if commits < MIN_ANALYTICS_COMMITS:
        out.append(f"GIT06: теку analytics/ змінено у {commits} комітах, потрібно щонайменше {MIN_ANALYTICS_COMMITS} "
                   "(спершу запити й масштабування, потім індекси та звіт)")
    if _git(project, "status", "--porcelain", "--", ".").stdout.strip():
        out.append("GIT04: є незафіксовані зміни у теці проєкту (git status)")
    return out


# ---------------------------------------------------------------- все разом


def deploy_and_check(project):
    """Розгортає проєкт у тимчасовій схемі, масштабує дані й перевіряє аналітику. Повертає (каталог, зауваження)."""
    out = []
    try:
        with scratch() as (cur, schema):
            catalog, problems = check_migrations(project, cur)
            out += problems
            if catalog is None:
                return None, out
            loaded, problems = run_load(project, cur, catalog)
            out += problems
            out += check_post_load(project, cur, catalog)
            out += check_analytics(project, cur, schema, catalog)
            return catalog, out
    except psycopg.OperationalError as exc:
        return None, [f"MIG00: немає з'єднання з PostgreSQL ({_first_line(exc)}); запустіть сервер і задайте PGHOST, PGPORT тощо"]


def _settings():
    return dict(host=os.environ.get("PGHOST", "localhost"), port=int(os.environ.get("PGPORT", "5432")),
                user=os.environ.get("PGUSER", "postgres"), password=os.environ.get("PGPASSWORD", "postgres"),
                dbname=os.environ.get("PGDATABASE", "postgres"))


def check_all(project, git=True):
    project = Path(project)
    catalog, out = deploy_and_check(project)
    if git:
        out += check_git(project)
    return out


def main(argv):
    project = Path(argv[1]) if len(argv) > 1 else Path(os.environ.get("PROJECT_DIR", ROOT.parent / "project"))
    problems = check_all(project)
    for p in problems:
        print(p)
    print(f"Зауважень: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
