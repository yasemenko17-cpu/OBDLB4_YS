-- title: Рейтинг продажів продуктів з віконною функцією
SELECT 
    p.title,
    SUM(oi.quantity) AS total_quantity,
    SUM(oi.quantity * oi.price) AS total_revenue,
    RANK() OVER (ORDER BY SUM(oi.quantity * oi.price) DESC) AS sales_rank
FROM order_item oi
JOIN product p ON oi.product_id = p.id
GROUP BY p.id, p.title
ORDER BY sales_rank, p.id;