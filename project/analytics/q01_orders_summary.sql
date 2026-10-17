-- title: Зведення замовлень за статусами
WITH order_stats AS (
    status, 
    COUNT(*) AS total_orders
    FROM orders
    GROUP BY status
)
SELECT status, total_orders
FROM order_stats
ORDER BY total_orders DESC;