# RqhBot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)
![Version](https://img.shields.io/badge/Version-3.7.0-orange.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![OneBot](https://img.shields.io/badge/OneBot-11-00b894.svg)
![NapCat](https://img.shields.io/badge/NapCat-supported-6c5ce7.svg)

基于 **NapCat OneBot11** 协议的 Python QQ 机器人框架。

</div>

---

## 三层结构

```
run.py
 └── sdk  3.7.0 (协议 / 插件 / 配置)
      └── plugins/  8 个插件
```

## 8 个插件

| 插件 | 功能 | 代码量 | 数据存储 |
|------|------|--------|----------|
| masu | AI 聊天（OpenAI） | ~350 行 | 内存 session |
| rqhspeech | 发言统计 / 排行榜 | ~700 行 | SQLite |
| rqhmain | 综合（运势/天气/新闻/词云/总结） | ~900 行 | JSONL |
| pintu | 拼图游戏 | ~500 行 | 内存 |
| rqhshen | 修仙游戏 | ~400 行 | JSON |
| rqhwenda | 问答匹配 | ~300 行 | JSON |
| theme_diary | 主题日记 | ~200 行 | Markdown |
| group_summary | 群聊总结 | ~200 行 | JSON |

## 数据流

```
用户消息 → NapCat WS → SDK EventBus → 插件 filter → 插件 handler → SDK API → NapCat → QQ
```

当前 SDK 特性：事件总线快照分发、filter 命中并发执行、任务异常统一记录、插件卸载顺序优化、`send_event_message` 统一回复。

## 核心模块

| 模块 | 说明 |
|------|------|
| `NapCatClient` | WebSocket 客户端 + OneBot API 封装 |
| `EventBus` | 事件总线（快照分发，并发 handler） |
| `PluginBase` | 插件基类（配置/数据/任务管理） |
| `PluginManager` | 插件加载与生命周期管理 |
| `BotClient` | 装饰器模式机器人入口 |

## 快速开始

```bash
pip install -r requirements.txt
cp config.yaml.example config.yaml   # 编辑配置
python run.py
```

## 项目结构

```text
rqhbot/
├── sdk/              # 框架核心
├── plugins/          # 8 个插件
├── docs/             # 文档
├── tests/            # 测试
├── config.yaml.example
├── requirements.txt
├── pyproject.toml
├── setup.py
└── run.py
```

## 一键安装

```bash
pip install .
```

---

<div align="center">

**RqhBot v3.7.0**

</div>
