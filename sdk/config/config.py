"""
配置模块
YAML 配置管理、环境变量加载与日志系统，全部采用强类型声明
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, Optional, TypeAlias

import yaml
from dotenv import load_dotenv

# 日志器
logger = logging.getLogger(__name__)

# 加载环境变量
_env_path: Path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

# ---- 类型别名 ----
YamlConfig: TypeAlias = Dict[str, Any]


class ConfigManager:
    """YAML 配置管理器"""

    def __init__(self, config_path: str = "config.yaml") -> None:
        """初始化配置管理器

        Args:
            config_path: 配置文件路径
        """
        _raw: Path = Path(config_path)
        if not _raw.is_absolute():
            # 相对路径解析到项目根目录
            _raw = Path(__file__).parent.parent.parent / _raw
        self.config_path: Path = _raw
        self.config: YamlConfig = {}
        self._load_config()

    def _load_config(self) -> None:
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded: Any = yaml.safe_load(f)
                    self.config = loaded if isinstance(loaded, dict) else {}
            except Exception as e:
                logger.error("[配置] 加载失败: %s，使用空配置", e)
                self.config = {}
        else:
            self.config = {}

    def _save_config(self) -> None:
        """保存配置文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self.config,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
        except Exception as e:
            logger.error("[配置] 保存失败: %s", e)

    # ---- 通用读写 ----

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号分隔路径）

        Args:
            key: 配置键，如 'napcat.ws_url'
            default: 默认值

        Returns:
            配置值
        """
        keys: list[str] = key.split(".")
        value: Any = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """设置配置值（支持点号分隔路径）

        Args:
            key: 配置键
            value: 配置值
        """
        keys: list[str] = key.split(".")
        current: Any = self.config

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value

    def save(self) -> None:
        """保存配置到文件"""
        self._save_config()

    def reload(self) -> None:
        """重新加载配置"""
        self._load_config()

    def show(self) -> None:
        """显示当前配置"""
        config_str = yaml.dump(
            self.config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        logger.info("当前配置:\n%s", config_str)

    # ==================== NapCat 配置 ====================

    def set_bot_uin(self, bot_uin: str) -> None:
        """设置机器人 QQ 号"""
        self.set("napcat.bot_uin", bot_uin)
        self._save_config()

    def set_root(self, root: str) -> None:
        """设置根账号"""
        self.set("napcat.root", root)
        self._save_config()

    def set_ws_uri(self, ws_uri: str) -> None:
        """设置 WebSocket URI"""
        self.set("napcat.ws_url", ws_uri)
        self._save_config()

    def set_ws_token(self, ws_token: str) -> None:
        """设置 WebSocket Token"""
        self.set("napcat.access_token", ws_token)
        self._save_config()

    def set_webui_uri(self, webui_uri: str) -> None:
        """设置 WebUI URI"""
        self.set("napcat.webui_uri", webui_uri)
        self._save_config()

    def set_webui_token(self, webui_token: str) -> None:
        """设置 WebUI Token"""
        self.set("napcat.webui_token", webui_token)
        self._save_config()

    # ==================== Bot 配置 ====================

    def set_load_plugins(self, load_plugins: bool) -> None:
        """设置是否加载插件"""
        self.set("bot.load_plugins", load_plugins)
        self._save_config()

    def set_plugin_dir(self, plugin_dir: str) -> None:
        """设置插件目录"""
        self.set("bot.plugin_dir", plugin_dir)
        self._save_config()

    # ==================== 日志配置 ====================

    def set_log_level(self, level: str) -> None:
        """设置日志级别"""
        self.set("logging.level", level)
        self._save_config()

    def set_log_dir(self, log_dir: str) -> None:
        """设置日志目录"""
        self.set("logging.log_dir", log_dir)
        self._save_config()

    # ==================== 其他 ====================

    def set_debug(self, debug: bool) -> None:
        """设置调试模式"""
        self.set("settings.debug", debug)
        self._save_config()


# 全局配置实例
config_manager: ConfigManager = ConfigManager()


# ==================== 环境变量配置类 ====================

class Config:
    """环境变量配置类（兼容旧版）

    环境变量只在类定义时读取一次，提升性能。
    支持通过 reload_env() 热更新配置。
    """

    # NapCat 连接配置
    NAPCAT_WS_URL: str = os.getenv("NAPCAT_WS_URL", "ws://localhost:3001")
    NAPCAT_ACCESS_TOKEN: str = os.getenv("NAPCAT_ACCESS_TOKEN", "")

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

    # 机器人配置
    BOT_DEBUG: bool = os.getenv("BOT_DEBUG", "false").lower() == "true"

    @classmethod
    def reload_env(cls, env_file: Optional[str] = None) -> None:
        """重新加载环境变量（热更新用）

        Args:
            env_file: 环境变量文件路径，默认项目根目录 .env
        """
        if env_file:
            load_dotenv(env_file, override=True)
        else:
            load_dotenv(Path(__file__).parent.parent / ".env", override=True)
        # 更新类属性
        cls.NAPCAT_WS_URL = os.getenv("NAPCAT_WS_URL", cls.NAPCAT_WS_URL)
        cls.NAPCAT_ACCESS_TOKEN = os.getenv("NAPCAT_ACCESS_TOKEN", cls.NAPCAT_ACCESS_TOKEN)
        cls.LOG_LEVEL = os.getenv("LOG_LEVEL", cls.LOG_LEVEL)
        cls.LOG_DIR = os.getenv("LOG_DIR", cls.LOG_DIR)
        cls.BOT_DEBUG = os.getenv("BOT_DEBUG", str(cls.BOT_DEBUG)).lower() == "true"

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """获取配置值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值
        """
        return os.getenv(key, default)

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """获取布尔配置值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            布尔配置值
        """
        raw: str = os.getenv(key, str(default)).lower()
        return raw in ("true", "1", "yes", "y")


# ==================== 日志系统 ====================

_logging_setup_done: bool = False


def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[str] = None,
    backup_count: int = 30,
) -> None:
    """设置日志系统（按日期轮转，保留最近30天，幂等调用）

    Args:
        log_level: 日志级别，默认从 Config 读取
        log_dir: 日志目录，默认从 Config 读取
        backup_count: 保留的日志文件数量，默认30
    """
    global _logging_setup_done
    if _logging_setup_done:
        return
    _logging_setup_done = True

    level: str = log_level if log_level is not None else Config.LOG_LEVEL
    directory: str = log_dir if log_dir is not None else Config.LOG_DIR

    # 创建日志目录
    log_path: Path = Path(directory)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file: Path = log_path / "bot.log"

    # 根日志器
    root: logging.Logger = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    # 文件处理器（按日期轮转）
    fh: logging.handlers.TimedRotatingFileHandler = (
        logging.handlers.TimedRotatingFileHandler(
            str(log_file),
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
        )
    )
    fh.suffix = "%Y-%m-%d"
    fh.setLevel(getattr(logging, level.upper(), logging.INFO))
    fh.setFormatter(logging.Formatter(Config.LOG_FORMAT))
    root.addHandler(fh)

    # 控制台处理器
    ch: logging.StreamHandler = logging.StreamHandler()
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch.setFormatter(logging.Formatter(Config.LOG_FORMAT))
    root.addHandler(ch)

    # 抑制第三方库日志
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取日志器

    Args:
        name: 日志器名称

    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)
