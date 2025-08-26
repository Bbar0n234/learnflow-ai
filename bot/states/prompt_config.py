"""FSM states for prompt configuration flow"""

from aiogram.fsm.state import State, StatesGroup


class PromptConfigStates(StatesGroup):
    """States for prompt configuration menu navigation"""
    
    # Main menu state
    main_menu = State()
    
    # Profile selection states
    selecting_profile_category = State()  # Choosing between style/subject profiles
    selecting_profile = State()  # Choosing specific profile from category
    
    # Placeholder configuration states
    selecting_placeholder = State()  # Choosing placeholder to modify
    selecting_value = State()  # Choosing value for selected placeholder
    
    # Settings view state
    viewing_settings = State()  # Viewing current settings
    
    # Confirmation states
    confirming_reset = State()  # Confirming reset to defaults
    confirming_profile = State()  # Confirming profile application