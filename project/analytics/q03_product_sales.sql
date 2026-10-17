-- title: Рейтинг продажів продуктів
SELECT 
    p.name,
    SUM(oi.quantity) AS total_quantity,
    RANK() OVER (ORDER BY SUM(oi.quantity) DESC) AS sales_rank
FROM order_item oi
JOIN product p ON oi.product_id = p.id
GROUP BY p.id, p.name
ORDER BY sales_rank, p.id;