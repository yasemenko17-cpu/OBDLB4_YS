-- Параметри планувальника, які фіксують тести лабораторної. Виконайте на початку сеансу psql: \i session.sql
SET jit = off;
SET max_parallel_workers_per_gather = 0;
SET default_statistics_target = 1000;
SET random_page_cost = 1.1;
SET effective_cache_size = '1GB';
