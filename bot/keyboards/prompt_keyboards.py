"""Keyboard layouts for prompt configuration management"""

from typing import List, Optional, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..models.prompt_config import (
    Profile,
    UserSettings,
    Placeholder,
    PlaceholderValue,
    UserPlaceholderSetting,
)


def build_main_menu_keyboard(user_settings: Optional[UserSettings] = None) -> InlineKeyboardMarkup:
    """
    Build main prompt configuration menu
    
    Args:
        user_settings: Current user settings (optional)
    
    Returns:
        InlineKeyboardMarkup: Main menu keyboard
    """
    keyboard = []
    
    # Profile selection button
    keyboard.append([
        InlineKeyboardButton(
            text="📚 Выбрать профиль",
            callback_data="prompt_select_profile_category"
        )
    ])
    
    # Detailed settings button
    keyboard.append([
        InlineKeyboardButton(
            text="⚙️ Детальная настройка",
            callback_data="prompt_select_placeholder"
        )
    ])
    
    # View current settings button
    keyboard.append([
        InlineKeyboardButton(
            text="📋 Мои настройки",
            callback_data="prompt_view_settings"
        )
    ])
    
    # Reset to defaults button
    keyboard.append([
        InlineKeyboardButton(
            text="🔄 Сброс к дефолтным",
            callback_data="prompt_reset_confirm"
        )
    ])
    
    # Close menu button
    keyboard.append([
        InlineKeyboardButton(
            text="❌ Закрыть",
            callback_data="prompt_close"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_profile_category_keyboard() -> InlineKeyboardMarkup:
    """
    Build profile category selection keyboard
    
    Returns:
        InlineKeyboardMarkup: Category selection keyboard
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="📝 Стили изложения",
                callback_data="prompt_category_style"
            )
        ],
        [
            InlineKeyboardButton(
                text="📖 Предметные области",
                callback_data="prompt_category_subject"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="prompt_main_menu"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_profiles_keyboard(
    profiles: List[Profile],
    category: str,
    page: int = 0,
    page_size: int = 5
) -> InlineKeyboardMarkup:
    """
    Build profile selection keyboard with pagination
    
    Args:
        profiles: List of profiles to display
        category: Category name for back button
        page: Current page number
        page_size: Number of items per page
    
    Returns:
        InlineKeyboardMarkup: Profile selection keyboard
    """
    keyboard = []
    
    # Calculate pagination
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(profiles))
    total_pages = (len(profiles) + page_size - 1) // page_size
    
    # Add profile buttons
    for profile in profiles[start_idx:end_idx]:
        display_text = f"{profile.display_name}"
        if profile.description:
            display_text = f"{profile.display_name[:30]}..."
        
        keyboard.append([
            InlineKeyboardButton(
                text=display_text,
                callback_data=f"prompt_apply_profile:{profile.id}"
            )
        ])
    
    # Pagination buttons
    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"prompt_profiles_page:{category}:{page-1}"
            )
        )
    
    if total_pages > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data="prompt_noop"
            )
        )
    
    if page < total_pages - 1:
        pagination_row.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"prompt_profiles_page:{category}:{page+1}"
            )
        )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Back button
    keyboard.append([
        InlineKeyboardButton(
            text="🔙 К категориям",
            callback_data="prompt_select_profile_category"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_placeholder_selection_keyboard(
    placeholders: Dict[str, UserPlaceholderSetting],
    page: int = 0,
    page_size: int = 8
) -> InlineKeyboardMarkup:
    """
    Build placeholder selection keyboard with pagination
    
    Args:
        placeholders: Dictionary of placeholder settings
        page: Current page number
        page_size: Number of items per page
    
    Returns:
        InlineKeyboardMarkup: Placeholder selection keyboard
    """
    keyboard = []
    
    # Convert to list for pagination
    placeholder_list = list(placeholders.values())
    
    # Calculate pagination
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(placeholder_list))
    total_pages = (len(placeholder_list) + page_size - 1) // page_size
    
    # Add placeholder buttons
    for setting in placeholder_list[start_idx:end_idx]:
        display_text = f"{setting.placeholder_display_name}: {setting.display_name[:20]}"
        if len(setting.display_name) > 20:
            display_text += "..."
        
        keyboard.append([
            InlineKeyboardButton(
                text=display_text,
                callback_data=f"prompt_edit_placeholder:{setting.placeholder_id}"
            )
        ])
    
    # Pagination buttons
    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"prompt_placeholders_page:{page-1}"
            )
        )
    
    if total_pages > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data="prompt_noop"
            )
        )
    
    if page < total_pages - 1:
        pagination_row.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"prompt_placeholders_page:{page+1}"
            )
        )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Back to main menu button
    keyboard.append([
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="prompt_main_menu"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_value_selection_keyboard(
    values: List[PlaceholderValue],
    placeholder_id: str,
    current_value_id: Optional[str] = None,
    page: int = 0,
    page_size: int = 8
) -> InlineKeyboardMarkup:
    """
    Build value selection keyboard for a placeholder
    
    Args:
        values: List of available values
        placeholder_id: ID of the placeholder being edited
        current_value_id: Currently selected value ID
        page: Current page number
        page_size: Number of items per page
    
    Returns:
        InlineKeyboardMarkup: Value selection keyboard
    """
    keyboard = []
    
    # Calculate pagination
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(values))
    total_pages = (len(values) + page_size - 1) // page_size
    
    # Add value buttons
    for value in values[start_idx:end_idx]:
        # Mark current value
        prefix = "✅ " if value.id == current_value_id else ""
        display_text = f"{prefix}{value.display_name[:35]}"
        if len(value.display_name) > 35:
            display_text += "..."
        
        keyboard.append([
            InlineKeyboardButton(
                text=display_text,
                callback_data=f"prompt_set_value:{placeholder_id}:{value.id}"
            )
        ])
    
    # Pagination buttons
    pagination_row = []
    if page > 0:
        pagination_row.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"prompt_values_page:{placeholder_id}:{page-1}"
            )
        )
    
    if total_pages > 1:
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data="prompt_noop"
            )
        )
    
    if page < total_pages - 1:
        pagination_row.append(
            InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"prompt_values_page:{placeholder_id}:{page+1}"
            )
        )
    
    if pagination_row:
        keyboard.append(pagination_row)
    
    # Back to placeholder list button
    keyboard.append([
        InlineKeyboardButton(
            text="🔙 К настройкам",
            callback_data="prompt_select_placeholder"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_settings_view_keyboard(
    user_settings: UserSettings,
    page: int = 0,
    page_size: int = 10
) -> InlineKeyboardMarkup:
    """
    Build keyboard for viewing current settings
    
    Args:
        user_settings: User's current settings
        page: Current page number
        page_size: Number of items per page
    
    Returns:
        InlineKeyboardMarkup: Settings view keyboard
    """
    keyboard = []
    
    # Convert to list for pagination
    placeholder_list = list(user_settings.placeholders.values())
    
    # Calculate pagination
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(placeholder_list))
    total_pages = (len(placeholder_list) + page_size - 1) // page_size
    
    # Add setting display and edit buttons (2 columns)
    for i in range(start_idx, end_idx, 2):
        row = []
        for j in range(i, min(i + 2, end_idx)):
            setting = placeholder_list[j]
            row.append(
                InlineKeyboardButton(
                    text=f"✏️ {setting.placeholder_display_name[:15]}",
                    callback_data=f"prompt_edit_placeholder:{setting.placeholder_id}"
                )
            )
        keyboard.append(row)
    
    # Pagination buttons
    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=f"prompt_settings_page:{page-1}"
                )
            )
        
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data="prompt_noop"
            )
        )
        
        if page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=f"prompt_settings_page:{page+1}"
                )
            )
        
        keyboard.append(pagination_row)
    
    # Back to main menu button
    keyboard.append([
        InlineKeyboardButton(
            text="🔙 Главное меню",
            callback_data="prompt_main_menu"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_reset_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Build confirmation keyboard for reset action
    
    Returns:
        InlineKeyboardMarkup: Confirmation keyboard
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Да, сбросить",
                callback_data="prompt_reset_confirmed"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="prompt_main_menu"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def format_main_menu_message(user_settings: Optional[UserSettings] = None) -> str:
    """
    Format the main menu message
    
    Args:
        user_settings: Current user settings
    
    Returns:
        Formatted message string
    """
    message = "🎨 **Настройка промптов**\n\n"
    
    if user_settings and user_settings.active_profile_name:
        message += f"📌 **Активный профиль:** {user_settings.active_profile_name}\n\n"
    else:
        message += "📌 **Активный профиль:** Индивидуальные настройки\n\n"
    
    message += (
        "Выберите действие:\n\n"
        "• **Выбрать профиль** - быстрая настройка под задачу\n"
        "• **Детальная настройка** - изменить отдельные параметры\n"
        "• **Мои настройки** - просмотреть текущие значения\n"
        "• **Сброс** - вернуть дефолтные значения"
    )
    
    return message


def format_settings_message(user_settings: UserSettings) -> str:
    """
    Format message showing current settings
    
    Args:
        user_settings: User's current settings
    
    Returns:
        Formatted settings message
    """
    message = "📋 **Текущие настройки промптов**\n\n"
    
    if user_settings.active_profile_name:
        message += f"**Профиль:** {user_settings.active_profile_name}\n\n"
    
    # Show first few settings as preview
    preview_count = min(5, len(user_settings.placeholders))
    for i, (name, setting) in enumerate(user_settings.placeholders.items()):
        if i >= preview_count:
            break
        message += f"• **{setting.placeholder_display_name}:** {setting.display_name}\n"
    
    if len(user_settings.placeholders) > preview_count:
        remaining = len(user_settings.placeholders) - preview_count
        message += f"\n_...и еще {remaining} настроек_\n"
    
    message += "\n_Нажмите на кнопку для изменения параметра_"
    
    return message


def format_profile_applied_message(profile_name: str) -> str:
    """
    Format message for successful profile application
    
    Args:
        profile_name: Name of applied profile
    
    Returns:
        Success message
    """
    return f"✅ **Профиль применен**\n\nПрофиль **{profile_name}** успешно применен к вашим настройкам."


def format_placeholder_updated_message(
    placeholder_name: str,
    value_name: str
) -> str:
    """
    Format message for successful placeholder update
    
    Args:
        placeholder_name: Display name of placeholder
        value_name: Display name of new value
    
    Returns:
        Success message
    """
    return (
        f"✅ **Настройка обновлена**\n\n"
        f"**{placeholder_name}** изменен на:\n_{value_name}_"
    )