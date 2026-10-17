"""Три набори даних лабораторної роботи: назви таблиць і стовпців, обсяги й генерація даних засобами generate_series.

Усі дані детерміновані: вони обчислюються з номера рядка арифметикою цілих чисел, без random(), тому на будь-якому
сервері PostgreSQL 18 таблиці вийдуть однаковими. Структура всіх трьох наборів однакова (особа, позиція, подія);
різняться назви, обсяги, діапазон дат, слова статусів і словники.
"""

SETS = {
    1: dict(
        title="Магазин",
        person="customer", p_id="id", p_name="full_name", p_email="email", p_city="city", p_since="registered_on",
        item="product", i_id="id", i_code="sku", i_title="title", i_kind="category", i_price="price",
        fact="sale", f_id="id", f_person="customer_id", f_item="product_id", f_qty="qty", f_amount="amount",
        f_status="status", f_at="sold_at", f_tags="tags", f_attrs="attrs", f_memo="memo",
        done="paid", open="new", bad="cancelled", code_prefix="SKU-",
        n_fact=120000, n_person=20000, n_item=400, start="2024-01-01", step_min=5,
        kinds=["Молочні", "Хліб", "Овочі", "Напої", "Бакалія", "Побутова хімія", "Солодощі", "Заморожене"],
    ),
    2: dict(
        title="Бібліотека",
        person="reader", p_id="id", p_name="full_name", p_email="email", p_city="city", p_since="joined_on",
        item="book", i_id="id", i_code="isbn", i_title="title", i_kind="genre", i_price="price",
        fact="loan", f_id="id", f_person="reader_id", f_item="book_id", f_qty="copies", f_amount="fee",
        f_status="state", f_at="loaned_at", f_tags="labels", f_attrs="details", f_memo="remark",
        done="returned", open="open", bad="lost", code_prefix="ISBN-",
        n_fact=100000, n_person=15000, n_item=600, start="2024-03-01", step_min=6,
        kinds=["Проза", "Поезія", "Наука", "Історія", "Дитяча", "Фантастика", "Довідники", "Мемуари", "Детектив"],
    ),
    3: dict(
        title="Фітнес-клуб",
        person="member", p_id="id", p_name="full_name", p_email="email", p_city="city", p_since="joined_on",
        item="workout", i_id="id", i_code="code", i_title="title", i_kind="kind", i_price="price",
        fact="visit", f_id="id", f_person="member_id", f_item="workout_id", f_qty="places", f_amount="paid",
        f_status="state", f_at="visited_at", f_tags="flags", f_attrs="meta", f_memo="comment",
        done="attended", open="booked", bad="missed", code_prefix="WK-",
        n_fact=110000, n_person=12000, n_item=60, start="2024-02-01", step_min=5,
        kinds=["Йога", "Кардіо", "Силові", "Плавання", "Пілатес", "Танці"],
    ),
}

FIRST = ["Олена", "Іван", "Марія", "Андрій", "Софія", "Тарас", "Наталія", "Богдан", "Ірина", "Максим", "Оксана", "Дмитро"]
LAST = ["Коваленко", "Шевченко", "Бондаренко", "Мельник", "Ткаченко", "Кравченко", "Олійник", "Поліщук", "Лисенко", "Мороз"]
CITIES = ["Київ", "Львів", "Одеса", "Харків", "Дніпро", "Запоріжжя", "Вінниця", "Полтава", "Чернівці", "Луцьк"]
TAGS = ["new", "sale", "gift", "fast", "bulk", "eco", "promo", "late", "repeat", "online", "pickup", "retail", "cold", "fragile",
        "season", "local", "import", "trial", "bonus", "return", "express", "plain", "night", "weekend", "campus",
        "family", "senior", "group", "solo", "mixed"]
CHANNELS = ["web", "shop", "phone", "app", "partner"]
WORDS = ["якість", "доставка", "швидко", "повільно", "дякуємо", "помилка", "знижка", "повтор", "ранок", "вечір", "склад",
         "відділ", "касир", "картка", "готівка", "рахунок", "акція", "подарунок", "обмін", "термін", "упаковка", "чек",
         "клієнт", "запит", "відгук", "оплата", "пошта", "курʼєр", "адреса", "підпис", "залишок", "партія", "серія",
         "новинка", "сезон", "резерв", "зал", "тренер", "група", "абонемент", "каталог", "фонд", "читач", "полиця",
         "видача", "повернення", "борг", "штраф", "продовження", "запис", "розклад", "перенесення", "скасування",
         "оновлення", "перевірка", "облік", "звіт", "архів", "доплата", "відмова"]
RARE_TAG = "vip"
RARE_WORD = "гарантія"


def h(salt):
    """SQL-вираз детермінованого 32-бітного хеша номера рядка g (md5): рівномірний розподіл без зв'язків між стовпцями."""
    return f"('x' || substr(md5(g::text || '{salt}'), 1, 8))::bit(32)::bigint"


def lit(values):
    return "ARRAY[" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + "]"


def person_table_sql(D):
    P = D
    n = D["n_person"]
    return f"""
CREATE TABLE {P['person']} (
    {P['p_id']} integer PRIMARY KEY,
    {P['p_name']} text NOT NULL,
    {P['p_email']} text,
    {P['p_city']} text NOT NULL,
    {P['p_since']} date NOT NULL
) WITH (autovacuum_enabled = false);
INSERT INTO {P['person']}
SELECT g,
       (({lit(FIRST)})[1 + g % 12]) || ' ' || (({lit(LAST)})[1 + (g / 12) % 10]),
       CASE WHEN g % 3 = 0 THEN 'User' || g || '@Example.com' ELSE 'user' || g || '@example.com' END,
       ({lit(CITIES)})[1 + (g * 7) % 10],
       date '2023-01-01' + ((g * 37) % 700)::integer
FROM generate_series(1::bigint, {n}::bigint) AS g;
-- повторні записи однієї особи: електронна пошта відрізняється регістром і пробілами
INSERT INTO {P['person']}
SELECT {n} + j, {P['p_name']}, ' ' || upper({P['p_email']}) || ' ', {P['p_city']}, {P['p_since']} + 200
FROM generate_series(1, 40) AS j JOIN {P['person']} o ON o.{P['p_id']} = j * 97;
INSERT INTO {P['person']}
SELECT {n} + 40 + j, {P['p_name']}, lower({P['p_email']}) || '  ', {P['p_city']}, {P['p_since']} + 300
FROM generate_series(1, 5) AS j JOIN {P['person']} o ON o.{P['p_id']} = j * 97;
-- особи без пошти не вважаються дублікатами
INSERT INTO {P['person']}
SELECT {n} + 45 + j, 'Без пошти ' || j, NULL, 'Київ', date '2024-01-01'
FROM generate_series(1, 6) AS j;
"""


def item_table_sql(D):
    P = D
    return f"""
CREATE TABLE {P['item']} (
    {P['i_id']} integer PRIMARY KEY,
    {P['i_code']} text NOT NULL UNIQUE,
    {P['i_title']} text NOT NULL,
    {P['i_kind']} text NOT NULL,
    {P['i_price']} numeric(10,2) NOT NULL
) WITH (autovacuum_enabled = false);
INSERT INTO {P['item']}
SELECT g, '{P['code_prefix']}' || lpad(g::text, 4, '0'), 'Позиція ' || g,
       ({lit(P['kinds'])})[1 + g % {len(P['kinds'])}],
       10 + (g * 37) % 490
FROM generate_series(1::bigint, {P["n_item"]}::bigint) AS g;
"""


def fact_table_sql(D):
    P = D
    n, npers, nitem = P["n_fact"], P["n_person"] + 45, P["n_item"]
    total_min = n * P["step_min"]
    return f"""
CREATE TABLE {P['fact']} (
    {P['f_id']} integer PRIMARY KEY,
    {P['f_person']} integer NOT NULL,
    {P['f_item']} integer NOT NULL,
    {P['f_qty']} integer NOT NULL,
    {P['f_amount']} numeric(12,2) NOT NULL,
    {P['f_status']} text NOT NULL,
    {P['f_at']} timestamp NOT NULL,
    {P['f_tags']} text[] NOT NULL,
    {P['f_attrs']} jsonb NOT NULL,
    {P['f_memo']} text NOT NULL
) WITH (autovacuum_enabled = false);
INSERT INTO {P['fact']}
SELECT g,
       CASE WHEN g % 10 < 3 THEN 1 + {h('hot')} % 200
            ELSE 1 + {h('person')} % {npers} END,
       1 + {h('item')} % {nitem},
       1 + g % 5,
       ((g * 37) % 950 + 50) + ((g * 13) % 100) / 100.0,
       CASE WHEN g % 100 = 0 THEN '{P['open']}' WHEN g % 100 BETWEEN 1 AND 5 THEN '{P['bad']}' ELSE '{P['done']}' END,
       timestamp '{P['start']} 00:00' + ({h('time')} % {total_min}) * interval '1 minute',
       ARRAY[({lit(TAGS)})[1 + g % 30], ({lit(TAGS)})[1 + (g * 7) % 30]]
           || CASE WHEN g % 1500 = 0 THEN ARRAY['{RARE_TAG}'] ELSE ARRAY[]::text[] END,
       jsonb_build_object('channel', ({lit(CHANNELS)})[1 + g % 5],
                          'sku', 'SKU-' || lpad(((g * 13) % 2000)::text, 4, '0'),
                          'gift', g % 997 = 0),
       ({lit(WORDS)})[1 + g % 60] || ' ' || ({lit(WORDS)})[1 + (g * 7) % 60] || ' ' || ({lit(WORDS)})[1 + (g * 11) % 60]
           || ' ' || ({lit(WORDS)})[1 + (g * 13) % 60] || CASE WHEN g % 2500 = 0 THEN ' {RARE_WORD}' ELSE '' END
FROM generate_series(1::bigint, {n}::bigint) AS g;
"""


def build_sql(set_no, analyze=True):
    D = SETS[set_no]
    text = person_table_sql(D) + item_table_sql(D) + fact_table_sql(D)
    if analyze:
        text += f"ANALYZE {D['person']}; ANALYZE {D['item']}; ANALYZE {D['fact']};\n"
    return text
