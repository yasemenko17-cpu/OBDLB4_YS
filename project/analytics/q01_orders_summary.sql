-- title: Зведення замовлень за статусами та загальна сума
WITH order_stats AS (
    SELECT 
        status, 
        COUNT(*) AS total_orders, 
        SUM(total_amount) AS total_sum
    FROM orders
    GROUP BY status
)
SELECT status, total_orders, total_sum
FROM order_stats
ORDER BY total_sum DESC;