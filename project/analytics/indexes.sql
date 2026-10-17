DROP INDEX IF EXISTS idx_orders_customer_status;
DROP INDEX IF EXISTS idx_orders_cancelled_date;

CREATE INDEX idx_orders_customer_status ON orders (customer_id, status);
CREATE INDEX idx_orders_cancelled_date ON orders (status, order_date) WHERE status = 'cancelled';