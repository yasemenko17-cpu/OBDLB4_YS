"""Задача 8. Вираз в умові: індекс за виразом або переписування запиту.

Опис і умови: student.md, розділ «Опис задач», задача 8; картка вашого варіанта.
"""

# Впишіть номер свого варіанта (22-24).
VARIANT = 23


import psycopg
from psycopg import sql

VARIANT = 23

def fix():
    # 1. Список команд для створення індексу за виразом
    indexes = [
        "CREATE INDEX loan_date_trunc_idx ON loan (date_trunc('day', loaned_at))"
    ]
    
    # 2. Вихідний запит із використанням параметра %(v)s
    query = """
        SELECT id 
        FROM loan 
        WHERE date_trunc('day', loaned_at) = %(v)s 
        ORDER BY id
    """
    
    return indexes, query