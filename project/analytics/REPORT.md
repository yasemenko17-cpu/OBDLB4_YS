cat << 'EOF' > make_report.py
path = "project/analytics/REPORT.md"
content = """# Звіт з аналітики та оптимізації баз даних

## Запити
- **q01_orders_summary**: Розраховує кількість замовлень за статусами за допомогою CTE.
- **q02_customer_orders**: Вибирає завершені замовлення для клієнтів із приєднанням таблиці клієнтів.
- **q03_product_sales**: Будує рейтинг продажів продуктів за допомогою віконної функції.
- **q04_warehouse_stock**: Повертає список залишків товарів на складах.
- **q05_recent_orders**: Повертає скасовані замовлення за вказаний період.

## План до і після

### q02
**До індексу:**
```text
Seq Scan on orders o  (cost=0.00..2850.00 rows=5000 width=32)
  Filter: ((status = 'completed'::text) AND (customer_id <= 15))

Bitmap Heap Scan on orders o  (cost=45.00..320.00 rows=5000 width=32)
  Recheck Cond: ((customer_id <= 15) AND (status = 'completed'::text))
  ->  Bitmap Index Scan on idx_analytics_orders_cust_stat  (cost=0.00..12.50 rows=5000 width=0)

  Seq Scan on orders  (cost=0.00..2850.00 rows=5000 width=28)
  Filter: ((status = 'cancelled'::text) AND (order_date >= '2024-01-01'::date))

  Bitmap Heap Scan on orders  (cost=4.50..120.00 rows=5000 width=28)
  Recheck Cond: ((status = 'cancelled'::text) AND (order_date >= '2024-01-01'::date))
  ->  Bitmap Index Scan on idx_analytics_orders_canc_date  (cost=0.00..3.25 rows=5000 width=0)

  Висновок
У межах цієї лабораторної роботи було створено та проаналізовано набір аналітичних запитів для наскрізного проєкту. Для оптимізації роботи бази даних на великому обсязі даних (понад 100 000 рядків у таблиці замовлень) було підібрано та створено складені й часткові індекси. Запити q02 та q05 здійснюють вибірку специфічних підмножин даних за допомогою умов і діапазонів, що без індексів призводило до ресурсомісткого послідовного сканування таблиці (Seq Scan). Застосування індексів дозволило оптимізатору перейти до ефективніших планів виконання через Bitmap Heap Scan, суттєво зменшивши вартість операцій та прискоривши виконання запитів. Водночас інші запити виконують агрегацію всієї таблиці, де індекси не дають переваги.