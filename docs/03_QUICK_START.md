# 快速开始指南

## 🎯 5 分钟上手 RqhBot

## 📋 前置要求

- Python 3.8+
- NapCat 已安装并登录 QQ
- 基本的 Python 知识

## 🚀 安装步骤

### 1. 克隆项目

```bash
git clone https://github.com/your-repo/rqhbot.git
cd rqhbot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置连接

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`，设置 NapCat 连接信息：

```yaml
napcat:
  ws_url: "ws://127.0.0.1:3002"
  access_token: ""                  # NapCat 访问令牌
```

### 4. 启动

```bash
python run.py
```

## ✅ 验证

启动后可以看到：

```
==================================================
  RqhBot - QQ机器人
==================================================
WebSocket: ws://127.0.0.1:3002
插件系统: 启用
==================================================
正在连接...
连接成功！
```

在 QQ 中发送消息，机器人加载的插件将按规则响应。

## 📝 自定义机器人

创建 `my_bot.py`：

```python
from sdk import BotClient, GroupMessageEvent

bot = BotClient()

@bot.on_group_message()
async def handle_message(msg: GroupMessageEvent):
    if msg.message.plain_text == "ping":
        await bot.api.send_group_message(msg.group_id, "pong!")

if __name__ == "__main__":
    bot.start(load_plugins=False)
```

```bash
python my_bot.py
```

## 🔧 基础配置

```yaml
bot:
  load_plugins: true    # 是否加载插件
  plugin_dir: "plugins"

logging:
  level: "INFO"         # DEBUG / INFO / WARNING / ERROR

settings:
  debug: false
```

## 🎓 下一步

- [配置指南](./04_CONFIG_GUIDE.md) — 详细配置说明
- [插件开发](./06_PLUGIN_DEVELOPMENT.md) — 开发自己的插件
- [API 参考](./05_API.md) — 完整 API 文档

## ❓ 常见问题

| 问题 | 解决 |
|------|------|
| 连接失败 | 检查 NapCat 是否运行、ws_url 是否正确 |
| 插件不加载 | 确认 `config.yaml` 中 `load_plugins: true` |
| 查看日志 | 日志文件在 `log/` 目录，按日期命名 |

---

**版本**: 3.5.0
