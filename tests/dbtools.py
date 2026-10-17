"""Робота з PostgreSQL у тестах: з'єднання, тимчасові схеми, клонування даних, розбір планів EXPLAIN.

Параметри з'єднання беруться зі змінних середовища PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE (у Codespaces вони
вже задані). Типові значення: localhost, 5432, postgres, postgres, postgres.

Щоб плани були відтворюваними, кожен сеанс тестів фіксує параметри планувальника (див. PLANNER). Таблиці трьох наборів
генеруються один раз за сеанс pytest у шаблонній схемі, а кожен тест отримує свою копію у власній схемі lab03_<токен>.
Усі схеми видаляються після тестів.
"""
import atexit
import os
import re
import uuid

import psycopg
import pytest

from domains import SETS, build_sql

PLANNER = {
    "jit": "off",
    "max_parallel_workers_per_gather": "0",
    "default_statistics_target": "1000",
    "random_page_cost": "1.1",
    "effective_cache_size": "1GB",
    "statement_timeout": "60000",
}

TABLE_SCANS = ("Seq Scan", "Index Scan", "Index Only Scan", "Bitmap Heap Scan")
INDEX_SCANS = ("Index Scan", "Index Only Scan", "Bitmap Index Scan")


def settings():
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ.get("PGUSER", "postgres"),
        "password": os.environ.get("PGPASSWORD", "postgres"),
        "dbname": os.environ.get("PGDATABASE", "postgres"),
    }


def connect(schema=None, autocommit=True, planner=True):
    cfg = settings()
    options = []
    if schema:
        options.append(f"-c search_path={schema}")
    if planner:
        options += [f"-c {k}={v}" for k, v in PLANNER.items()]
    try:
        conn = psycopg.connect(connect_timeout=5, options=" ".join(options), **cfg)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Немає з'єднання з PostgreSQL ({cfg['host']}:{cfg['port']}): {exc}\n"
            "Запустіть сервер: у Codespaces він стартує разом із середовищем; локально виконайте\n"
            "  docker run --name lab-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:18\n"
            "і за потреби задайте PGHOST, PGPORT, PGUSER, PGPASSWORD.",
            pytrace=False)
    conn.autocommit = autocommit
    return conn


# ------------------------------------------------------------------ шаблонні дані

_templates = {}
_token = uuid.uuid4().hex[:8]


def template_schema(set_no):
    """Схема з повною копією даних набору; створюється один раз за сеанс."""
    if set_no not in _templates:
        name = f"lab03_tpl{set_no}_{_token}"
        boot = connect(autocommit=True, planner=False)
        boot.execute(f'CREATE SCHEMA "{name}"')
        boot.close()
        conn = connect(name)
        conn.execute(build_sql(set_no, analyze=False))
        conn.close()
        _templates[set_no] = name
    return _templates[set_no]


def drop_templates():
    if not _templates:
        return
    try:
        conn = connect(autocommit=True, planner=False)
        for name in list(_templates.values()):
            conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    _templates.clear()


atexit.register(drop_templates)


# ------------------------------------------------------------------ середовище тесту

class Lab:
    """Тимчасова схема одного тесту й засоби для даних, запитів, планів та індексів."""

    def __init__(self):
        self.schema = "lab03_" + uuid.uuid4().hex[:10]
        self.conn = None
        self._extra = []

    def __enter__(self):
        boot = connect(autocommit=True, planner=False)
        boot.execute(f'CREATE SCHEMA "{self.schema}"')
        boot.close()
        self.conn = connect(self.schema)
        self._cur = psycopg.ClientCursor(self.conn)
        return self

    def __exit__(self, *exc):
        for conn in [self.conn, *self._extra]:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            cleaner = connect(autocommit=True, planner=False)
            cleaner.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            cleaner.close()
        except Exception:  # noqa: BLE001
            pass

    # --- дані

    def use(self, set_no, *roles, analyze=True):
        """Копіює таблиці набору в схему тесту. roles: 'person', 'item', 'fact'. Повертає словник назв набору."""
        D = SETS[set_no]
        tpl = template_schema(set_no)
        for role in roles or ("person", "item", "fact"):
            name = D[role]
            self.sql(f'CREATE TABLE "{name}" (LIKE "{tpl}"."{name}" INCLUDING ALL) WITH (autovacuum_enabled = false)')
            self.sql(f'INSERT INTO "{name}" SELECT * FROM "{tpl}"."{name}"')
        if analyze:
            for role in roles or ("person", "item", "fact"):
                self.sql(f'ANALYZE "{D[role]}"')
        return D

    def sql(self, text, params=None):
        self._cur.execute(text, params)

    def rows(self, text, params=None):
        self._cur.execute(text, params)
        return [tuple(r) for r in self._cur.fetchall()] if self._cur.description else []

    def value(self, text, params=None):
        return self.rows(text, params)[0][0]

    # --- плани

    def plan(self, text, params=None, analyze=False):
        """Корінь плану EXPLAIN (FORMAT JSON) як словник (ключ "Plan")."""
        options = "ANALYZE, TIMING OFF, BUFFERS OFF, FORMAT JSON" if analyze else "FORMAT JSON"
        self._cur.execute(f"EXPLAIN ({options}) " + text, params)
        return self._cur.fetchone()[0][0]

    def raw_plan(self, text, params=None, analyze=False):
        """Те саме, що plan(), але у вигляді, який повертає сервер: список з одного словника."""
        options = "ANALYZE, TIMING OFF, BUFFERS OFF, FORMAT JSON" if analyze else "FORMAT JSON"
        self._cur.execute(f"EXPLAIN ({options}) " + text, params)
        return self._cur.fetchone()[0]

    def new_connection(self, autocommit=False):
        """Окреме з'єднання в схемі тесту; за замовчуванням без автофіксації, як у вашому коді."""
        conn = connect(self.schema, autocommit=autocommit)
        self._extra.append(conn)
        return conn

    # --- індекси

    def indexes(self):
        """{ім'я індексу: (таблиця, метод, текст визначення)} для всіх індексів схеми тесту."""
        rows = self.rows(
            "SELECT i.indexname, i.tablename, am.amname, i.indexdef FROM pg_indexes i "
            "JOIN pg_class c ON c.relname = i.indexname JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = i.schemaname "
            "JOIN pg_am am ON am.oid = c.relam WHERE i.schemaname = %s", (self.schema,))
        return {r[0]: (r[1], r[2], r[3]) for r in rows}

    def apply_ddl(self, statements, table=None, limit=3):
        """Виконує команди CREATE INDEX студента й повертає імена нових індексів."""
        if isinstance(statements, str):
            statements = [statements]
        if not isinstance(statements, (list, tuple)) or not statements or not all(isinstance(s, str) for s in statements):
            pytest.fail("Функція має повертати непорожній список рядків із командами CREATE INDEX", pytrace=False)
        before = set(self.indexes())
        for text in statements:
            body = re.sub(r"'(?:[^']|'')*'", "''", text).strip().rstrip(";").strip()
            if ";" in body or not re.match(r"(?is)^create\s+(unique\s+)?index\b", body):
                pytest.fail(f"Дозволено лише окремі команди CREATE INDEX, без «;» усередині. Отримано: {text.strip()[:120]!r}",
                            pytrace=False)
            try:
                self.sql(text)
            except psycopg.Error as exc:
                pytest.fail(f"Сервер відхилив команду {text.strip()[:120]!r}: {str(exc).strip().splitlines()[0]}", pytrace=False)
        new = sorted(set(self.indexes()) - before)
        if len(new) > limit:
            pytest.fail(f"Створено {len(new)} індексів, а для цього запиту достатньо не більше {limit}: кожен зайвий індекс уповільнює зміни даних",
                        pytrace=False)
        return new

    def index_columns(self, name):
        """[(ім'я стовпця або вираз, чи входить до ключа)] у порядку індексу."""
        rows = self.rows(
            "SELECT pg_get_indexdef(i.indexrelid, k.n, true), k.n <= i.indnkeyatts "
            "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "CROSS JOIN LATERAL generate_series(1, i.indnatts) AS k(n) WHERE c.relname = %s AND n.nspname = %s ORDER BY k.n",
            (name, self.schema))
        return rows

    def index_size(self, name):
        return self.value("SELECT pg_relation_size(%s::regclass)", (f'"{self.schema}"."{name}"',))

    def index_has_predicate(self, name):
        return self.value("SELECT i.indpred IS NOT NULL FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                          "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = %s AND n.nspname = %s",
                          (name, self.schema))


# ------------------------------------------------------------------ розбір планів (для перевірок тестів)

def walk(node):
    """Вузли плану в прямому порядку обходу."""
    yield node
    for child in node.get("Plans", []):
        yield from walk(child)


def scans(plan):
    return [n for n in walk(plan["Plan"]) if n["Node Type"] in TABLE_SCANS]


def used_indexes(plan):
    out = []
    for n in walk(plan["Plan"]):
        if n["Node Type"] in INDEX_SCANS and n.get("Index Name") not in out:
            out.append(n["Index Name"])
    return out


def describe(plan):
    return " → ".join(
        f"{n['Node Type']}" + (f" на {n['Relation Name']}" if n.get("Relation Name") else "") + (f" ({n['Index Name']})" if n.get("Index Name") else "")
        for n in walk(plan["Plan"]) if n["Node Type"] in TABLE_SCANS + ("Bitmap Index Scan", "Sort", "Incremental Sort"))
