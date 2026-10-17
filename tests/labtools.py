"""Спільні засоби відкритих і повних тестів: реєстр випадків, доступ до функцій студента, перевірні помічники."""
import inspect
import re

import psycopg
import pytest
from conftest import load

# Задачі, у яких функція повертає текст для конкретного набору: у студента вона без параметрів (набір визначає VARIANT),
# в еталоні перший параметр це номер набору.
PER_SET = {1, 2, 3, 5, 6, 7, 8, 9}


class Cases:
    """Реєстр випадків однієї задачі: кожен випадок належить набору умов S1, S2 або S3."""

    def __init__(self):
        self.items = []

    def case(self, sset, public=False):
        def register(fn):
            self.items.append((sset, fn))
            return fn
        return register

    def params(self):
        return [(s, fn) for s, fn in self.items]

    def ids(self, prefix):
        return [f"{prefix}-{s}-{fn.__name__}" for s, fn in self.items]


class Api:
    """Доступ до функцій задачі: студентського файла (перевіряє VARIANT) або еталона (приймає номер набору)."""

    def __init__(self, task, sset):
        self.task = task
        self.sset = sset
        self.module = load(task)
        self.reference = bool(getattr(self.module, "REFERENCE", False))
        if not self.reference:
            variant = getattr(self.module, "VARIANT", 0)
            if not variant:
                pytest.fail("Змінну VARIANT не задано: впишіть номер свого варіанта (1-30) на початку файла", pytrace=False)
            if (variant - 1) // 3 + 1 != task:
                pytest.fail(f"VARIANT = {variant} не відповідає задачі {task}: файл lab_{task:02d}.py призначений "
                            f"для варіантів {3 * task - 2}-{3 * task}", pytrace=False)
            if (variant - 1) % 3 + 1 != sset:
                pytest.skip("перевірка іншого набору даних")

    def call(self, name, *args, **kwargs):
        fn = getattr(self.module, name, None)
        if fn is None:
            pytest.fail(f"У файлі задачі {self.task} немає функції {name}()", pytrace=False)
        if self.reference and self.task in PER_SET:
            args = (self.sset, *args)
        try:
            return fn(*args, **kwargs)
        except NotImplementedError:
            pytest.fail(f"Функцію {name}() ще не реалізовано (NotImplementedError)", pytrace=False)


def api(task, sset):
    return Api(task, sset)


def run_select(lab, text, params=None, timeout_ms=30000):
    """Виконує запит студента в режимі «лише читання» з обмеженням часу; повертає (кількість стовпців, рядки)."""
    if not isinstance(text, str) or not text.strip():
        pytest.fail("Функція має повертати непорожній рядок із запитом", pytrace=False)
    sql = text.strip()
    while sql.endswith(";"):
        sql = sql[:-1].rstrip()
    body = re.sub(r"'(?:[^']|'')*'", "''", sql)
    if ";" in body:
        pytest.fail("Має бути рівно один запит: приберіть зайві «;» і додаткові команди", pytrace=False)
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        pytest.fail("Запит має починатися зі SELECT або WITH; змінювати дані й схему не можна", pytrace=False)
    lab.sql("SET default_transaction_read_only = on")
    lab.sql(f"SET statement_timeout = {timeout_ms}")
    try:
        cur = lab.conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        return len(cur.description), rows
    except psycopg.errors.QueryCanceled:
        pytest.fail("Запит виконується надто довго (понад 30 с): імовірно, забуто умову з'єднання або запит читає зайве", pytrace=False)
    except psycopg.Error as exc:
        pytest.fail(f"Помилка SQL {exc.sqlstate}: {str(exc).strip().splitlines()[0]}", pytrace=False)
    finally:
        if not idle(lab.conn):
            lab.conn.rollback()
        lab.sql("SET default_transaction_read_only = off")
        lab.sql("SET statement_timeout = 60000")


def same_rows(got, want, ordered=True, what="результат"):
    """Порівнює таблиці значень (числа за величиною); при розбіжності показує перші відмінності."""
    from decimal import Decimal

    def norm(v):
        if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
            return Decimal(str(v)).normalize() if v == v else v
        return v

    g = [tuple(norm(v) for v in r) for r in got]
    w = [tuple(norm(v) for v in r) for r in want]
    if not ordered:
        g, w = sorted(g, key=repr), sorted(w, key=repr)
    if g == w:
        return
    if len(g) != len(w):
        pytest.fail(f"{what}: рядків {len(g)}, очікувалось {len(w)}. Перший рядок результату: {g[0] if g else None}; очікувався: {w[0] if w else None}",
                    pytrace=False)
    for i, (a, b) in enumerate(zip(g, w)):
        if a != b:
            pytest.fail(f"{what}: рядок {i + 1} відрізняється: отримано {a}, очікувалось {b}", pytrace=False)


def idle(conn):
    return conn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE


def add_line(lab, D, id, person, item, amount, at, status=None, qty=3, tags=(), attrs="{}", memo=""):
    """Додає рядок у таблицю подій набору (для крайніх випадків закритих тестів)."""
    status = status or D["done"]
    lab.sql(
        f'INSERT INTO "{D["fact"]}" VALUES (%s, %s, %s, %s, %s, %s, %s, %s::text[], %s::jsonb, %s)',
        (id, person, item, qty, amount, status, at, list(tags), attrs, memo))


def add_item(lab, D, id, code, kind, price=100, title="Тестова позиція"):
    lab.sql(f'INSERT INTO "{D["item"]}" VALUES (%s, %s, %s, %s, %s)', (id, code, title, kind, price))


def add_person(lab, D, id, email, name="Тест Тестович", city="Київ", since="2024-01-01"):
    lab.sql(f'INSERT INTO "{D["person"]}" VALUES (%s, %s, %s, %s, %s)', (id, name, email, city, since))
