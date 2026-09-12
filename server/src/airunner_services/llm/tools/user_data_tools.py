"""Legacy user data storage helpers (no longer registered as LLM tools).

These functions write/read fields on the User model and have been superseded
by record_knowledge / recall_knowledge which use the knowledge_facts table.
They are kept here as plain functions (not decorated with @tool) so that any
existing call-sites still import successfully.
"""

from airunner_services.database.models.user import User


def store_user_data(key: str, value: str) -> str:
    """Store a field on the User model (legacy, prefer record_knowledge)."""
    try:
        user = User.objects.get_or_create()
        setattr(user, key, value)
        user.save()
        return f"Stored {key}: {value}"
    except Exception as e:
        return f"Error storing data: {str(e)}"


def get_user_data(key: str) -> str:
    """Read a field from the User model (legacy, prefer recall_knowledge)."""
    try:
        user = User.objects.get_or_create()
        value = getattr(user, key, None)
        if value is None:
            return f"No data found for key: {key}"
        return str(value)
    except Exception as e:
        return f"Error retrieving data: {str(e)}"
