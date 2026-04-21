import os
import json

CONFIG_PATH = os.path.expanduser("~/.freshconfig")


def get_global_model():
    """
    Reads the global model selection from ~/.freshconfig.
    Returns 'gpt-4o' as default if not configured.
    """
    if not os.path.exists(CONFIG_PATH):
        return "gpt-4o"

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("model_name", "gpt-4o")
    except Exception:
        return "gpt-4o"


def set_global_model(model_name: str):
    """
    Writes the selected model string to ~/.freshconfig.
    """
    data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    data["model_name"] = model_name

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_max_intents():
    """
    Reads the max intents per swarm from ~/.freshconfig.
    Returns 10 as default if not configured.
    """
    if not os.path.exists(CONFIG_PATH):
        return 10

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("max_intents_per_swarm", 10)
    except Exception:
        return 10


def set_max_intents(count: int):
    """
    Writes the max intents per swarm to ~/.freshconfig.
    """
    data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    data["max_intents_per_swarm"] = count

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
