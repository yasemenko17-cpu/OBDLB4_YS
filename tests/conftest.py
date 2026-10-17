"""Допоміжний завантажувач: підключає файл задачі з теки variants/ і дає тестам фікстуру lab."""
import importlib.util
import os
import signal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


def load(number):
    """Повертає модуль задачі з номером number."""
    base = Path(os.environ.get("VARIANT_DIR", ROOT.parent / "variants"))
    for prefix in ("variant", "lab", "task"):
        path = base / f"{prefix}_{number:02d}.py"
        if path.exists():
            spec = importlib.util.spec_from_file_location(f"{prefix}_{number:02d}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError(f"Не знайдено файл задачі {number:02d} у {base}")


@pytest.fixture(autouse=True)
def _watchdog():
    """Тест, що завис, завершується за 120 с (запити студента мають власне обмеження statement_timeout)."""
    def boom(signum, frame):
        raise TimeoutError("тест завис довше 120 с: перевірте запит або цикли у вашому коді")
    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(120)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


@pytest.fixture(scope="session", autouse=True)
def _templates():
    """Після сеансу видаляє шаблонні схеми з даними наборів."""
    yield
    import dbtools
    dbtools.drop_templates()


@pytest.fixture
def lab():
    """Тимчасова схема на сервері й засоби для даних, планів та індексів; після тесту все видаляється."""
    from dbtools import Lab
    with Lab() as environment:
        yield environment
