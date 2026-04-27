"""Клавиатуры admin_load и стабильность реэкспорта `keyboard_factory` после распила."""
from src.bot.keyboards.keyboard_factory import create_not_enough_leads_keyboard, get_segment_emoji


def test_not_enough_keyboard_default_load_leads_prefix():
    kb = create_not_enough_leads_keyboard(7)
    row = kb.inline_keyboard[0][0]
    assert row.callback_data == "load_leads_confirm_available:7"


def test_not_enough_keyboard_bitrix_prefix():
    kb = create_not_enough_leads_keyboard(7, confirm_callback_prefix="load_bitrix")
    row = kb.inline_keyboard[0][0]
    assert row.callback_data == "load_bitrix_confirm_available:7"


def test_factory_reexports_get_segment_emoji():
    assert get_segment_emoji("Производство") == "🏭"
    assert get_segment_emoji("Другое") == "📦"
