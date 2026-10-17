-- Міграція V003: Створення індексів для зовнішніх ключів
CREATE INDEX "idx_product_category_id" ON "product" ("category_id");