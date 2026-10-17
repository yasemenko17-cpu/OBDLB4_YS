-- title: Залишки товарів на складах
SELECT w.location AS warehouse_location, p.name AS product_name, s.quantity
FROM stock s
JOIN warehouse w ON s.warehouse_id = w.id
JOIN product p ON s.product_id = p.id
WHERE s.quantity > 0
ORDER BY s.quantity DESC;