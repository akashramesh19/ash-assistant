from datetime import datetime

TOOL_DEFINITION = {
    "name": "get_time",
    "description": "Get the current local date and time.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def run(**kwargs) -> str:
    return datetime.now().strftime("%A, %d %B %Y, %H:%M:%S")
