SET search_path = project;

-- Індекс для прискорення q02 (customer_id, status)
CREATE INDEX idx_orders_customer_status ON orders (customer_id, status);

-- Чястковий/складений індекс для q05 (status, order_date)
CREATE INDEX idx_orders_cancelled_date ON orders (status, order_date) WHERE status = 'cancelled';