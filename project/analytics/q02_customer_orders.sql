-- title: Замовлення клієнтів ізфільтром за статусом
SELECT o.id, o.order_date, o.status, c.email
FROM orders o
JOIN customer c ON o.customer_id = c.id
WHERE o.status = 'completed' AND o.customer_id <= 15
ORDER BY o.order_date DESC, o.id DESC;