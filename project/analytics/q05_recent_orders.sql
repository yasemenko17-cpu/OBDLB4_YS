-- title: Недавні скасовані замовлення за період
SELECT id, customer_id, order_date, total_amount
FROM orders
WHERE status = 'cancelled' AND order_date >= '2024-06-01'
ORDER BY order_date DESC, id DESC;