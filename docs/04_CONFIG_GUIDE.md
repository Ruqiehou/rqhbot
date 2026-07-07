# 配置指南

## 📋 概述

RqhBot 使用 YAML 配置文件 `config.yaml`，项目提供 `config.yaml.example` 作为模板。

## 📁 配置文件结构

```yaml
# NapCat 连接
napcat:
  ws_url: "ws://127.0.0.1:3002"       # WebSocket 地址
  access_token: ""                      # 访问令牌
  bot_uin: ""                           # 机器人 QQ 号
  root: ""                              # 管理员 QQ 号
  webui_uri: "http://localhost:6098"    # WebUI 地址
  webui_token: ""                       # WebUI 令牌

# 机器人
bot:
  load_plugins: true                    # 是否加载插件
  plugin_dir: "plugins"                 # 插件目录

# 日志
logging:
  level: "INFO"                         # DEBUG/INFO/WARNING/ERROR/CRITICAL
  log_dir: "log"
  log_file: "bot.log"

# 设置
settings:
  debug: false
  auto_reconnect: true
  reconnect_interval: 5                 # 重连间隔（秒）
```

## 🔧 ConfigManager API

```python
from sdk.config import config_manager

# 获取配置（点号分隔路径）
ws_url = config_manager.get("napcat.ws_url", "ws://localhost:3002")
debug = config_manager.get("settings.debug", False)

# 设置配置（自动保存）
config_manager.set("settings.debug", True)

# 便捷方法（均自动保存）
config_manager.set_bot_uin("123456789")
config_manager.set_root("2654278608")
config_manager.set_ws_uri("ws://localhost:3002")
config_manager.set_ws_token("your_token")
config_manager.set_webui_uri("http://localhost:6098")
config_manager.set_webui_token("your_token")
config_manager.set_load_plugins(True)
config_manager.set_plugin_dir("plugins")
config_manager.set_log_level("DEBUG")
config_manager.set_log_dir("log")
config_manager.set_debug(False)

# 重新加载 / 查看
config_manager.reload()
config_manager.show()
```

## 💡 常用示例

### 初始化首次配置

```python
from sdk.config import config_manager
import os

if not os.path.exists("config.yaml"):
    config_manager.set_ws_uri("ws://127.0.0.1:3002")
    config_manager.set_load_plugins(True)
    print("默认配置已创建")
```

### 在启动脚本中使用

```python
from sdk.config import config_manager

ws_url = config_manager.get("napcat.ws_url", "ws://127.0.0.1:3002")
load_plugins = config_manager.get("bot.load_plugins", True)
plugin_dir = config_manager.get("bot.plugin_dir", "plugins")

bot.api.ws_url = ws_url
bot.start(load_plugins=load_plugins)
```

### 区分环境

```python
env = "production"
if env == "production":
    config_manager.set_debug(False)
    config_manager.set_log_level("WARNING")
else:
    config_manager.set_debug(True)
    config_manager.set_log_level("DEBUG")
```

## ⚠️ 注意事项

1. 所有 `set_*()` 方法调用后自动保存到 `config.yaml`
2. 配置优先级：命令行参数 > YAML > 环境变量 > 默认值
3. `config.yaml.example` 为模板，实际使用 `config.yaml`

---

**版本**: 3.5.0
