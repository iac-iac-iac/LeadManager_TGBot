"""Парсинг диапазона количества для «Мне повезёт!»."""
from typing import Optional, Tuple


def parse_lucky_leads_range(text: str) -> Optional[Tuple[int, int]]:
    """
    Два целых: минимум и максимум партии. Правила: 10 <= min <= max <= 200.

    Поддерживаемые форматы: «10-40», «10 25», длинное тире как минус.
    """
    raw = (
        text.strip()
        .replace("\u2014", "-")
        .replace("\u2013", "-")
    )
    if "-" in raw:
        parts = [p.strip() for p in raw.split("-", 1)]
    else:
        parts = raw.split()
    if len(parts) != 2:
        return None
    try:
        lo, hi = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if 10 <= lo <= hi <= 200:
        return lo, hi
    return None
