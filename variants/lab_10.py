"""Задача 10. Вплив ANALYZE: оцінка проти факту до і після збирання статистики.

Опис і умови: student.md, розділ «Опис задач», задача 10; картка вашого варіанта.
"""
import psycopg  # noqa: F401
from psycopg import sql  # noqa: F401

# Впишіть номер свого варіанта (28-30).
VARIANT = 0


def analyze_effect(conn, table: str, column: str, value: str) -> dict:
    """Вимірює оцінку планувальника й факт до та після ANALYZE таблиці; повертає словник {"before": ..., "after": ...}."""
    raise NotImplementedError("Реалізуйте analyze_effect() за описом задачі 10")
