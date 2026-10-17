-- title: Замовлення конкретного клієнта
SELECT o.id, o.order_date, o.status, o.total_amount, c.email
FROM orders o
JOIN customer c ON o.customer_id = c.id
WHERE o.customer_id = 5 AND o.status = 'completed'
ORDER BY o.order_date DESC, o.id DESC;