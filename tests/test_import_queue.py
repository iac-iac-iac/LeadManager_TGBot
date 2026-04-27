"""
Минимальные тесты BitrixImportQueue (§4 / §5.12 обзора).
"""
import pytest

from src.bitrix24.import_queue import BitrixImportQueue, get_import_queue, ImportTask, DuplicateCheckTask


def test_get_import_queue_singleton():
    a = get_import_queue()
    b = get_import_queue()
    assert a is b
    assert isinstance(a, BitrixImportQueue)


def test_queue_accepts_task_types():
    q = BitrixImportQueue()
    t1 = ImportTask([1, 2], "123", None, None)
    t2 = DuplicateCheckTask([1], None)
    assert t1.lead_ids == [1, 2]
    assert t2.lead_ids == [1]


def test_get_stats_shape():
    q = get_import_queue()
    s = q.get_stats()
    assert "processed" in s and "failed" in s and "total_leads" in s
    assert "queue_size" in s and "is_running" in s
