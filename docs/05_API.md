# RqhBot API 参考

## 目录

- [NapCatClient](#napcatclient) — 底层客户端
  - [消息发送](#消息发送)
  - [消息管理](#消息管理)
  - [互动功能](#互动功能)
  - [娱乐功能](#娱乐功能)
  - [消息历史](#消息历史)
  - [群组管理](#群组管理)
  - [好友管理](#好友管理)
  - [请求处理](#请求处理)
  - [通用 API](#通用-api-call)
- [PluginBase](#pluginbase) — 插件基类
- [事件类型](#事件类型)

---

## NapCatClient

底层 WebSocket 客户端，实现 `IClient` Protocol。插件中通过 `self.api` 访问。

### 访问方式

```python
# 主程序
await bot.api.send_group_message(group_id, "你好")

# 插件中（self.api 即 NapCatClient 实例）
await self.api.send_group_message(group_id, "你好")
```

### 消息发送

#### send_group_message(group_id, message, image_path, at_user_id, reply_message_id)

发送群消息。

```python
async def send_group_message(
    group_id: int,
    message: str = "",
    image_path: Optional[str] = None,
    at_user_id: Optional[int] = None,
    reply_message_id: Optional[int] = None
) -> Dict[str, Any]
```

**参数：**
- `group_id` (int): 群号
- `message` (str): 消息内容（可选，默认为空）
- `image_path` (str, optional): 图片文件路径
- `at_user_id` (int, optional): @ 的用户 ID
- `reply_message_id` (int, optional): 回复的消息 ID

**示例：**
```python
await self.api.send_group_message(123456, "大家好")
await self.api.send_group_message(123456, "你好", at_user_id=789012)
await self.api.send_group_message(123456, "收到", reply_message_id=12345)
```

#### send_private_message(user_id, message, image_path, reply_message_id)

发送私聊消息。

```python
async def send_private_message(
    user_id: int,
    message: str = "",
    image_path: Optional[str] = None,
    reply_message_id: Optional[int] = None
) -> Dict[str, Any]
```

**示例：**
```python
await self.api.send_private_message(789012, "你好")
```

#### send_group_message_segments(group_id, segments, reply_message_id)

发送群聊多格式混排消息（数组格式）。

```python
from sdk.core import MessageSegment

await self.api.send_group_message_segments(
    group_id=123456,
    segments=[
        MessageSegment.text("你好 "),
        MessageSegment.at(789012),
        MessageSegment.image("./images/demo.png", summary="示例图片"),
        MessageSegment.face(14),
    ],
)
```

**可用消息段：**

| 方法 | 说明 |
|------|------|
| `MessageSegment.text(content)` | 文本 |
| `MessageSegment.image(file, summary="")` | 图片（本地路径或 URL） |
| `MessageSegment.at(qq)` | @某人 |
| `MessageSegment.reply(message_id)` | 回复消息 |
| `MessageSegment.face(face_id)` | QQ 表情 |
| `MessageSegment.dice()` | 骰子 |
| `MessageSegment.rps()` | 猜拳 |
| `MessageSegment.json_data(data)` | JSON 卡片 |

#### send_private_message_segments(user_id, segments, reply_message_id)

发送私聊多格式混排消息，参数与群聊版本类似，目标从 `group_id` 改为 `user_id`。

### 消息管理

#### delete_message(message_id)

```python
async def delete_message(message_id: int) -> Dict[str, Any]
```

撤回/删除消息。

**示例：**
```python
result = await self.api.send_group_message(123456, "这条消息会被撤回")
await self.api.delete_message(result.get("message_id"))
```

#### get_message(message_id)

```python
async def get_message(message_id: int) -> Dict[str, Any]
```

获取指定消息的详细信息。

### 互动功能

#### group_poke(group_id, user_id)

群内戳一戳。

```python
await self.api.group_poke(123456, 789012)
```

#### friend_poke(user_id)

好友戳一戳。

```python
await self.api.friend_poke(789012)
```

### 娱乐功能

```python
await self.api.send_group_dice(123456)    # 群骰子
await self.api.send_group_rps(123456)     # 群猜拳
await self.api.send_private_dice(789012)  # 私聊骰子
await self.api.send_private_rps(789012)   # 私聊猜拳
```

### 消息历史

#### get_group_message_history(group_id, message_seq, count, reverse_order)

```python
history = await self.api.get_group_message_history(123456, count=20)
messages = history.get("messages", [])
```

#### get_private_message_history(user_id, message_seq, count, reverse_order)

```python
history = await self.api.get_private_message_history(789012, message_seq=0, count=10)
```

### 群组管理

```python
await self.api.get_group_list()
await self.api.get_group_member_list(123456)
await self.api.get_group_member_info(123456, 789012)
await self.api.set_group_ban(123456, 789012, duration=1800)   # 禁言
await self.api.set_group_kick(123456, 789012)                  # 踢出
await self.api.set_group_card(123456, 789012, "新名片")        # 设置名片
```

### 好友管理

```python
await self.api.get_friend_list()
await self.api.get_login_info()
await self.api.get_stranger_info(789012)
await self.api.send_like(789012, times=1)   # 点赞
```

### 请求处理

```python
await self.api.set_friend_add_request(flag="xxx", approve=True)
await self.api.set_group_add_request(flag="xxx", sub_type="add", approve=False, reason="理由")
```

### 通用 API: call

```python
async def call(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]
```

用于调用任意未封装的一通 API。

**示例：**
```python
group_info = await self.api.call("get_group_info", {"group_id": 123456})
friends = await self.api.call("get_friend_list")
result = await self.api.call("set_group_ban", {
    "group_id": 123456, "user_id": 789012, "duration": 600
})
```

---

## PluginBase

插件基类，所有插件必须继承此类。

### 核心方法

#### on_load(api, event_bus, plugin_dir)

插件加载时调用。

```python
async def on_load(self, api: IClient, event_bus: EventBus, plugin_dir: Optional[Path] = None)
```

**参数：**
- `api`: `IClient` 接口实例（实际为 `NapCatClient`），可调用 `api.send_group_message()` 等
- `event_bus`: `EventBus` 实例，用于订阅/发布事件
- `plugin_dir`: 插件目录路径

**示例：**
```python
async def on_load(self, api, event_bus, plugin_dir=None):
    await super().on_load(api, event_bus, plugin_dir)
    self.config = await self.load_config("config.json")
```

> 如果重写 `on_load()`，**必须**调用 `await super().on_load(api, event_bus, plugin_dir)`，否则过滤器不会订阅到事件总线。

#### on_unload()

插件卸载时调用。

```python
async def on_unload(self):
    await self.safe_save_data(self.cache, "data.json")
    await super().on_unload()
```

### 事件处理 — 过滤器装饰器

插件消息接收使用 `filter_registry` 装饰器。

| 装饰器 | 事件类型 | 用途 |
|--------|----------|------|
| `@filter_registry.group_server` | `GroupMessageEvent` | 群聊消息 |
| `@filter_registry.private_server` | `PrivateMessageEvent` | 私聊消息 |

**支持的过滤条件（可选参数）：**

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

多个条件同时写时是"并且"关系。

#### reply_with_event(event, content)

通过事件回复（自动识别群聊/私聊）。

```python
@filter_registry.group_server(equals="ping")
async def on_ping(self, event: GroupMessageEvent):
    await self.reply_with_event(event, "pong!")
```

### 工具方法

| 方法 | 说明 |
|------|------|
| `load_config(config_name)` | 加载插件配置（带缓存） |
| `save_config(config, config_name)` | 保存插件配置 |
| `safe_load_data(file_name, default)` | 安全加载 JSON 数据 |
| `safe_save_data(data, file_name)` | 安全保存 JSON 数据 |
| `create_task(coro)` | 创建后台任务（卸载时自动取消） |
| `delay(seconds)` | 异步延迟 |

### 属性

- `self.name` — 插件名称
- `self.version` — 插件版本
- `self.description` — 插件描述
- `self.author` — 作者
- `self.enabled` — 是否启用
- `self.api` — `IClient` 接口实例（`NapCatClient`）
- `self.event_bus` — `EventBus` 实例

---

## MessageSegment

消息段构建器，用于构建数组格式的多格式消息。

```python
from sdk.core import MessageSegment

segments = [
    MessageSegment.text("你好 "),
    MessageSegment.at(123456),
    MessageSegment.image("https://example.com/pic.png", summary="图片"),
    MessageSegment.face(14),
    MessageSegment.dice(),
    MessageSegment.rps(),
    MessageSegment.reply(10001),
]
```

## Message 对象

当 NapCat 上报数组格式消息时，SDK 会解析为 `Message` 对象：

| 字段 | 说明 |
|------|------|
| `event.message.plain_text` | 纯文本内容（适合命令判断） |
| `event.message.raw_message` | 原始字符串内容 |
| `event.message.segments` | 原始消息段列表（适合遍历图片/@等） |
| `event.message.face_ids` | 表情 ID 列表 |
| `event.message.has_dice` | 是否含骰子 |
| `event.message.has_rps` | 是否含猜拳 |

**示例：遍历图片和 @：**
```python
for segment in event.message.segments:
    seg_type = segment.get("type")
    data = segment.get("data", {})
    if seg_type == "image":
        print(data.get("file"))
    elif seg_type == "at":
        print(data.get("qq"))
```

---

## 事件类型

所有事件均为强类型 `dataclass`。

### GroupMessageEvent

```python
@dataclass
class GroupMessageEvent:
    time: int
    self_id: int
    message_type: str = "group"
    sub_type: str
    message_id: int
    group_id: int
    user_id: int
    user_name: str      # 优先取群名片，其次昵称
    message: Message
    raw_message: str
    sender: Dict
```

### PrivateMessageEvent

```python
@dataclass
class PrivateMessageEvent:
    time: int
    self_id: int
    message_type: str = "private"
    sub_type: str
    message_id: int
    user_id: int
    user_name: str
    message: Message
    raw_message: str
```

### NoticeEvent 子类

| 事件类 | 说明 |
|--------|------|
| `NoticeEvent` | 通知基类 |
| `GroupIncreaseNotice` | 群成员增加 |
| `GroupDecreaseNotice` | 群成员减少 |
| `GroupBanNotice` | 群禁言（含 duration） |
| `GroupRecallNotice` | 群消息撤回 |
| `FriendRecallNotice` | 好友消息撤回 |
| `PokeNotice` | 戳一戳通知 |

### RequestEvent 子类

| 事件类 | 说明 |
|--------|------|
| `RequestEvent` | 请求基类 |
| `FriendRequestEvent` | 好友申请 |
| `GroupRequestEvent` | 群邀请/加群申请（含 `group_id`/`sub_type`） |

---

## IClient 接口（Protocol）

插件通过此接口约束，确保与 `NapCatClient` 解耦。支持发送消息、群组管理、好友管理、API 调用等所有能力。

```python
from sdk.core.interfaces import IClient
```

---

**详细指南：** [插件开发指南](./06_PLUGIN_DEVELOPMENT.md) · [快速开始](./03_QUICK_START.md)
