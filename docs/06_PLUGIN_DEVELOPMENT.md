# 插件开发指南

## 🚀 快速开始

### 1. 创建插件目录

```bash
plugins/
└── hello/
    └── main.py
```

自动加载模式会扫描 `plugins/*/main.py`，并实例化其中继承 `PluginBase` 的插件类。

### 2. 最小插件示例

```python
import logging
from sdk.pluginsystem import PluginBase, filter_registry
from sdk.core.events import GroupMessageEvent, PrivateMessageEvent

logger = logging.getLogger(__name__)

class HelloPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "hello"
        self.version = "1.0.0"
        self.description = "Hello World 插件"
        self.author = "Your Name"

    @filter_registry.group_server
    async def hello_group(self, event: GroupMessageEvent):
        await self.reply_with_event(event, "你好！我是群聊机器人")

    @filter_registry.private_server
    async def hello_private(self, event: PrivateMessageEvent):
        await self.reply_with_event(event, "你好！我是私聊机器人")
```

---

## ✅ 插件必要内容

### 必要文件

| 文件 | 是否必要 | 说明 |
|------|----------|------|
| `plugins/插件名/main.py` | 必要 | 自动加载入口 |
| `plugins/插件名/__init__.py` | 可选 | 仅在手动包导入时需要 |
| `config.json` | 可选 | 插件配置文件 |
| 数据文件 | 可选 | 由插件自行读写 |

### 必要类

每个插件必须有一个继承 `PluginBase` 的类：

```python
from sdk.pluginsystem import PluginBase

class MyPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "my_plugin"
```

### 必要属性

| 属性 | 是否必要 | 说明 |
|------|----------|------|
| `self.name` | 必要 | 插件唯一名称，建议小写下划线 |
| `self.version` | 推荐 | 插件版本 |
| `self.description` | 推荐 | 插件描述 |
| `self.author` | 推荐 | 作者 |
| `self.enabled` | 可选 | 是否启用，默认 `True` |

### 禁止的旧写法

当前版本不兼容通过重写 `on_group_message()` / `on_private_message()` 接收消息。

```python
async def on_group_message(self, event):
    ...

async def on_private_message(self, event):
    ...
```

必须改成过滤器：

```python
@filter_registry.group_server
async def handle_group(self, event):
    ...

@filter_registry.private_server
async def handle_private(self, event):
    ...
```

---

## 🔍 消息过滤器

插件消息接收靠过滤器完成，分为群聊和私聊两种：

| 过滤器 | 事件类型 | 用途 |
|--------|----------|------|
| `@filter_registry.group_server` | `GroupMessageEvent` | 接收群聊消息 |
| `@filter_registry.private_server` | `PrivateMessageEvent` | 接收私聊消息 |

### 支持的过滤条件

| 参数 | 含义 | 示例 |
|------|------|------|
| `equals` | 文本完全等于 | `@filter_registry.group_server(equals="帮助")` |
| `keyword` | 包含单个关键词 | `@filter_registry.group_server(keyword="天气")` |
| `keywords` | 包含任意关键词 | `@filter_registry.group_server(keywords=["日榜", "周榜"])` |
| `contains` | 包含指定文本 | `@filter_registry.private_server(contains="查询")` |
| `prefix` | 指定前缀 | `@filter_registry.group_server(prefix="/天气")` |
| `prefixes` | 任意前缀 | `@filter_registry.group_server(prefixes=["/", "！"])` |
| `regex` | 正则匹配 | `@filter_registry.group_server(regex=r"^天气\s+(.+)$")` |
| `custom` | 自定义函数 | `@filter_registry.group_server(custom=is_admin)` |

多个条件同时写时是“并且”关系，全部满足才会触发。

---

## 🌿 推荐开发范式

### 范式 1：一个功能一个处理函数

不要把所有命令塞进一个大 `if/elif`，推荐按功能拆成多个过滤器函数。

```python
class MenuPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "menu"

    @filter_registry.group_server(equals="帮助")
    async def group_help(self, event: GroupMessageEvent):
        await self.reply_with_event(event, "群聊帮助菜单")

    @filter_registry.private_server(equals="帮助")
    async def private_help(self, event: PrivateMessageEvent):
        await self.reply_with_event(event, "私聊帮助菜单")
```

### 范式 2：分支条件写在过滤器里

```python
class RankPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "rank"

    @filter_registry.group_server(equals="日榜")
    async def daily_rank(self, event: GroupMessageEvent):
        await self.reply_with_event(event, "这里是日榜")

    @filter_registry.group_server(equals="周榜")
    async def weekly_rank(self, event: GroupMessageEvent):
        await self.reply_with_event(event, "这里是周榜")

    @filter_registry.group_server(equals="月榜")
    async def monthly_rank(self, event: GroupMessageEvent):
        await self.reply_with_event(event, "这里是月榜")
```

### 范式 3：需要解析参数时用 prefix 或 regex

```python
class WeatherPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "weather"

    @filter_registry.group_server(prefix="天气")
    async def group_weather(self, event: GroupMessageEvent):
        text = event.message.plain_text.strip()
        city = text.removeprefix("天气").strip()
        if not city:
            await self.reply_with_event(event, "请发送：天气 北京")
            return

        await self.reply_with_event(event, f"正在查询 {city} 的天气")

    @filter_registry.private_server(regex=r"^天气\s+(.+)$")
    async def private_weather(self, event: PrivateMessageEvent):
        text = event.message.plain_text.strip()
        city = text.split(maxsplit=1)[1]
        await self.reply_with_event(event, f"正在查询 {city} 的天气")
```

### 范式 4：复杂逻辑可以在处理函数内部继续分支

过滤器只负责粗筛，复杂业务可以继续写分支，但建议保持函数职责单一。

```python
class StatsPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "stats"

    @filter_registry.group_server(keywords=["日榜", "周榜", "月榜"])
    async def rank(self, event: GroupMessageEvent):
        text = event.message.plain_text.strip()

        if text == "日榜":
            await self.reply_with_event(event, "今日排行榜")
            return

        if text == "周榜":
            await self.reply_with_event(event, "本周排行榜")
            return

        if text == "月榜":
            await self.reply_with_event(event, "本月排行榜")
            return
```

### 范式 5：群聊和私聊分开写

群聊和私聊上下文不同，推荐分开处理，不要在一个函数里通过 `hasattr(event, "group_id")` 判断。

```python
class EchoPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "echo"

    @filter_registry.group_server(prefix="复读")
    async def group_echo(self, event: GroupMessageEvent):
        text = event.message.plain_text.removeprefix("复读").strip()
        await self.api.send_group_message(event.group_id, text)

    @filter_registry.private_server(prefix="复读")
    async def private_echo(self, event: PrivateMessageEvent):
        text = event.message.plain_text.removeprefix("复读").strip()
        await self.api.send_private_message(event.user_id, text)
```

---

## 🔧 生命周期函数

### on_load(api, event_bus, plugin_dir)

可选。插件加载时调用，适合加载配置、初始化缓存、创建后台任务。

```python
async def on_load(self, api, event_bus, plugin_dir=None):
    await super().on_load(api, event_bus, plugin_dir)
    self.config = await self.load_config("config.json")
```

如果重写 `on_load()`，必须调用：

```python
await super().on_load(api, event_bus, plugin_dir)
```

否则过滤器不会订阅到事件总线。

### on_unload()

可选。插件卸载时调用，适合保存数据、清理资源。

```python
async def on_unload(self):
    await self.safe_save_data(self.cache, "data.json")
    await super().on_unload()
```

---

## 🧩 多格式混排消息

多格式混排使用 `MessageSegment` 构建消息段，再通过 `send_group_message_segments()` 或 `send_private_message_segments()` 发送。

```python
from sdk.core import MessageSegment

class MixedMessagePlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self.name = "mixed_message"

    @filter_registry.group_server(equals="混排")
    async def mixed(self, event: GroupMessageEvent):
        await self.api.send_group_message_segments(
            group_id=event.group_id,
            segments=[
                MessageSegment.text("你好 "),
                MessageSegment.at(event.user_id),
                MessageSegment.text("，这是图文混排："),
                MessageSegment.image("./images/demo.png", summary="示例图片"),
                MessageSegment.face(14),
            ],
        )
```

接收多格式消息时：

```python
@filter_registry.group_server(keyword="图片")
async def parse_image(self, event: GroupMessageEvent):
    images = []

    for segment in event.message.segments:
        if segment.get("type") == "image":
            images.append(segment.get("data", {}).get("file"))

    if images:
        await self.reply_with_event(event, f"收到 {len(images)} 张图片")
```

---

## 📦 配置和数据

### 配置管理

```python
async def on_load(self, api, event_bus, plugin_dir=None):
    await super().on_load(api, event_bus, plugin_dir)
    self.config = await self.load_config("config.json")

async def save_my_config(self):
    self.config["enabled"] = True
    await self.save_config(self.config, "config.json")
```

### 数据持久化

```python
async def on_load(self, api, event_bus, plugin_dir=None):
    await super().on_load(api, event_bus, plugin_dir)
    self.data = await self.safe_load_data("data.json", {})

async def save_data(self):
    await self.safe_save_data(self.data, "data.json")
```

---

## 💡 最佳实践

1. 新插件统一使用 `@filter_registry.group_server` / `@filter_registry.private_server`。
2. 不再把所有逻辑写进 `on_group_message()`。
3. 一个处理函数只处理一个明确功能。
4. 命令判断优先使用 `equals`、`prefix`、`keywords`、`regex`。
5. 群聊和私聊分开写，避免上下文判断混乱。
6. 处理函数内部遇到错误要捕获，并回复友好提示。
7. 如果重写 `on_load()`，必须调用 `await super().on_load(...)`。
8. 纯文本判断用 `event.message.plain_text.strip()`。
9. 图片、@、表情等结构化内容遍历 `event.message.segments`。

---

## 📚 相关文档

- [API 参考](./05_API.md) — NapCatClient 和 PluginBase 详细说明
- [快速开始](./03_QUICK_START.md) — 项目入门指南
- [配置指南](./04_CONFIG_GUIDE.md) — 配置系统说明
- [架构概览](./02_OVERVIEW.md) — 架构设计说明

---

**插件开发范式：必要类 + 可选生命周期 + 群聊/私聊过滤器。**
