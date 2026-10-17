-- title: Залишки товарів на складах
SELECT w.name AS warehouse_name, p.title AS product_name, s.quantity
FROM stock s
JOIN warehouse w ON s.warehouse_id = w.id
JOIN product p ON s.product_id = p.id
WHERE s.quantity > 0
ORDER BY s.quantity DESC, s.id;