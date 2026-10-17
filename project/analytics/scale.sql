SET search_path = project;

INSERT INTO orders (id, customer_id, order_date, status, total)
SELECT 
    i AS id,
    ((i * 17) % 30) + 1 AS customer_id,
    '2024-01-01'::date + (i % 365) * INTERVAL '1 day' AS order_date,
    CASE WHEN i % 10 = 0 THEN 'cancelled' WHEN i % 5 = 0 THEN 'pending' ELSE 'completed' END AS status,
    ((i * 123) % 5000 + 100)::numeric(10,2) AS total
FROM generate_series(100, 100099) AS s(i)
ON CONFLICT (id) DO NOTHING;