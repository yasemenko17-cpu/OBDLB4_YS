CREATE INDEX IF NOT EXISTS idx_orders_customer_status ON orders (customer_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_cancelled_date ON orders (status, order_date) WHERE status = 'cancelled';