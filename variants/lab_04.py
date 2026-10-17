"""Задача 4. Розбір плану EXPLAIN (FORMAT JSON): вузли читання, індекси, оцінка проти факту.

Опис і умови: student.md, розділ «Опис задач», задача 4; картка вашого варіанта.
Функція не звертається до сервера: вона отримує вже розібраний JSON плану.
"""

# Впишіть номер свого варіанта (10-12).
VARIANT = 0


def summarize_plan(plan: list) -> dict:
    """Підсумок плану: ключі scans, indexes, has_sort, worst_misestimate, heap_fetches (див. розділ 7 інструкції)."""
    raise NotImplementedError("Реалізуйте summarize_plan() за описом задачі 4")
