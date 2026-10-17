-- title: Недавні скасовані замовлення
SELECT id, customer_id, order_date, status
FROM orders
WHERE status = 'cancelled' AND order_date >= '2024-01-01'
ORDER BY order_date DESC, id DESC;