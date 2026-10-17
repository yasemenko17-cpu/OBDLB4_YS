CREATE INDEX idx_analytics_orders_cust_stat ON orders (customer_id, status);
CREATE INDEX idx_analytics_orders_canc_date ON orders (status, order_date) WHERE status = 'cancelled';