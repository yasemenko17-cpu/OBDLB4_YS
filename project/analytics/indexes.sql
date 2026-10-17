CREATE INDEX idx_orders_customer_status ON orders (customer_id, status);
CREATE INDEX idx_orders_cancelled_date ON orders (status, order_date) WHERE status = 'cancelled';