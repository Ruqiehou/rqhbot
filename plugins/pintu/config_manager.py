import json
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_CONFIG = {
    "admins": ["2654278608"]
}

_config = None


def load_config():
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except Exception:
        config = DEFAULT_CONFIG.copy()

    if "admins" not in config or not isinstance(config["admins"], list):
        config["admins"] = DEFAULT_CONFIG["admins"].copy()
        save_config(config)

    config["admins"] = [str(user_id) for user_id in config.get("admins", [])]

    if not config["admins"]:
        # 空列表会让插件永远无法引导出第一个管理员（开拼图/加管都要求已是管理员），
        # 因此空列表回退到内置默认管理员，且不会给普通用户自我提权的机会。
        config["admins"] = [str(user_id) for user_id in DEFAULT_CONFIG["admins"]]
        save_config(config)

    group_admins = config.get("group_admins")
    if not isinstance(group_admins, dict):
        group_admins = {}
    config["group_admins"] = {
        str(group_id): [str(user_id) for user_id in members]
        for group_id, members in group_admins.items()
        if isinstance(members, list)
    }
    return config


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=4)


def get_config():
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_admins(group_id=None):
    """返回管理员列表；给定群号时返回 全局管理员 + 该群管理员（旧的扁平配置仍然有效）"""
    config = get_config()
    global_admins = list(config.get("admins", []))
    if group_id is None:
        return global_admins
    group_admins = config.get("group_admins", {}).get(str(group_id), [])
    merged = list(global_admins)
    for user_id in group_admins:
        if user_id not in merged:
            merged.append(user_id)
    return merged


def is_puzzle_admin(user_id, group_id=None):
    uid = str(user_id)
    config = get_config()
    if uid in [str(admin) for admin in config.get("admins", [])]:
        return True
    if group_id is None:
        return False
    group_admins = config.get("group_admins", {}).get(str(group_id), [])
    return uid in [str(admin) for admin in group_admins]


def add_admin(user_id, group_id=None):
    config = get_config()
    uid = str(user_id)
    if group_id is None:
        if uid in config["admins"]:
            return False
        config["admins"].append(uid)
    else:
        group_admins = config.setdefault("group_admins", {})
        members = group_admins.setdefault(str(group_id), [])
        if uid in members:
            return False
        members.append(uid)
    save_config(config)
    return True


def remove_admin(user_id, group_id=None):
    config = get_config()
    uid = str(user_id)
    if group_id is None:
        if uid not in config["admins"]:
            return False
        config["admins"].remove(uid)
    else:
        group_admins = config.get("group_admins", {})
        members = group_admins.get(str(group_id), [])
        if uid not in members:
            return False
        members.remove(uid)
        if not members:
            group_admins.pop(str(group_id), None)
    save_config(config)
    return True
