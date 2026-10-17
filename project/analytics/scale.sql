SET search_path = project;

-- Додаємо 100 000 рядків у таблицю orders (тільки існуючі стовпці)
INSERT INTO orders (id, order_date, status, customer_id)
SELECT 
    i AS id,
    '2024-01-01'::date + (i % 365) * INTERVAL '1 day' AS order_date,
    CASE WHEN i % 10 = 0 THEN 'cancelled' WHEN i % 5 = 0 THEN 'pending' ELSE 'completed' END AS status,
    ((i * 17) % 30) + 1 AS customer_id
FROM generate_series(100, 100099) AS s(i)
ON CONFLICT (id) DO NOTHING;

-- Додаємо позиції в order_item (тут є quantity і ціна через product)
INSERT INTO order_item (orders_id, item_no, quantity, product_id)
SELECT 
    i AS orders_id,
    1 AS item_no,
    (i % 5) + 1 AS quantity,
    ((i * 7) % 40) + 1 AS product_id
FROM generate_series(100, 100099) AS s(i)
ON CONFLICT (orders_id, item_no) DO NOTHING;