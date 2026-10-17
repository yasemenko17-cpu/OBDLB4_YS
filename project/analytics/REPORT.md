# Звіт з аналітики та оптимізації баз даних

## Запити
- **q01_orders_summary**: Розраховує загальні суми та кількість замовлень, згруповані за статусом за допомогою CTE.
- **q02_customer_orders**: Вибирає всі виконані замовлення для конкретного клієнта з приєднанням його пошти.
- **q03_product_sales**: Будує рейтинг продажів продуктів за допомогою агрегації та віконної функції RANK().
- **q04_warehouse_stock**: Повертає список залишків товарів на складах з об'єднанням трьох таблиць.
- **q05_recent_orders**: Повертає скасовані замовлення за вказаний період.

## План до і після

### q02
**До індексу:**
```text
Seq Scan on orders o  (cost=0.00..2850.00 rows=1500 width=32)
  Filter: ((status = 'completed'::text) AND (customer_id = 5))

**Після індексу:**
Index Scan using idx_orders_customer_status on orders o  (cost=0.42..15.25 rows=1500 width=32)
  Index Cond: ((customer_id = 5) AND (status = 'completed'::text))

q05 
До індексу:

Seq Scan on orders  (cost=0.00..2850.00 rows=5000 width=28)
  Filter: ((status = 'cancelled'::text) AND (order_date >= '2024-06-01'::date))

Після індексу:

Bitmap Heap Scan on orders  (cost=4.50..120.00 rows=5000 width=28)
  Recheck Cond: ((status = 'cancelled'::text) AND (order_date >= '2024-06-01'::date))
  ->  Bitmap Index Scan on idx_orders_cancelled_date  (cost=0.00..3.25 rows=5000 width=0)