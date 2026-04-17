"""
Пакет CRUD-операций для базы данных.

Реэкспортирует все функции для обратной совместимости:
    from src.database import crud
    await crud.get_user_by_telegram_id(...)  # работает как раньше
"""

from .leads import (
    create_lead,
    create_leads_batch,
    get_lead_by_id,
    get_leads_by_status,
    get_available_leads,
    count_available_leads,
    count_other_leads,
    get_other_leads_for_assignment,
    update_lead_status,
    assign_leads_to_manager,
    mark_lead_as_duplicate,
    mark_lead_as_unique,
    mark_lead_as_imported,
    delete_old_leads,
    get_available_leads_for_assignment,
    count_available_leads_for_assignment,
)

from .users import (
    create_user,
    get_user_by_telegram_id,
    get_user_by_full_name,
    get_pending_users,
    approve_user,
    reject_user,
    update_user_name,
    update_user_role,
    get_all_active_admins,
    get_all_active_users,
    get_active_managers_with_stats,
)

from .cities import (
    get_city,
    create_city,
    update_city_utc,
    get_all_cities,
    delete_city,
    create_pending_city,
    get_pending_cities,
    approve_pending_city,
    reject_pending_city,
)

from .segments import (
    get_segment_lock,
    freeze_segment,
    unfreeze_segment,
    get_all_segment_locks,
    is_segment_frozen,
    get_all_segments,
    get_segment_by_name,
    create_segment,
    sync_segments_from_leads,
    get_segments_with_cities,
)

from .tickets import (
    create_ticket,
    get_ticket_by_id,
    get_tickets_paginated,
    get_ticket_stats,
    update_ticket_status,
    add_admin_response,
    get_tickets_by_manager,
)

from .bot_status import (
    get_bot_status,
    set_bot_status,
    is_bot_running,
    is_bot_maintenance,
)

from .logs import (
    create_log,
    get_logs,
    get_logs_by_description,
    delete_old_logs,
    get_lead_stats_by_period,
    get_manager_stats,
)

__all__ = [
    # leads
    "create_lead",
    "create_leads_batch",
    "get_lead_by_id",
    "get_leads_by_status",
    "get_available_leads",
    "count_available_leads",
    "count_other_leads",
    "get_other_leads_for_assignment",
    "update_lead_status",
    "assign_leads_to_manager",
    "mark_lead_as_duplicate",
    "mark_lead_as_unique",
    "mark_lead_as_imported",
    "delete_old_leads",
    "get_available_leads_for_assignment",
    "count_available_leads_for_assignment",
    # users
    "create_user",
    "get_user_by_telegram_id",
    "get_user_by_full_name",
    "get_pending_users",
    "approve_user",
    "reject_user",
    "update_user_name",
    "update_user_role",
    "get_all_active_admins",
    "get_all_active_users",
    "get_active_managers_with_stats",
    # cities
    "get_city",
    "create_city",
    "update_city_utc",
    "get_all_cities",
    "delete_city",
    "create_pending_city",
    "get_pending_cities",
    "approve_pending_city",
    "reject_pending_city",
    # segments
    "get_segment_lock",
    "freeze_segment",
    "unfreeze_segment",
    "get_all_segment_locks",
    "is_segment_frozen",
    "get_all_segments",
    "get_segment_by_name",
    "create_segment",
    "sync_segments_from_leads",
    "get_segments_with_cities",
    # tickets
    "create_ticket",
    "get_ticket_by_id",
    "get_tickets_paginated",
    "get_ticket_stats",
    "update_ticket_status",
    "add_admin_response",
    "get_tickets_by_manager",
    # bot_status
    "get_bot_status",
    "set_bot_status",
    "is_bot_running",
    "is_bot_maintenance",
    # logs
    "create_log",
    "get_logs",
    "get_logs_by_description",
    "delete_old_logs",
    "get_lead_stats_by_period",
    "get_manager_stats",
]
