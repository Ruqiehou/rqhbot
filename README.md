# RqhBot - QQ 机器人PYTHON  SDK

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Version](https://img.shields.io/badge/Version-3.0.0-orange.svg)

一个基于 NapCat OneBot11 协议的 Python QQ 机器人开发框架

[📚 文档](docs/01_INDEX.md) • [⚡ 快速开始](docs/03_QUICK_START.md) • [🔌 插件开发](docs/06_PLUGIN_DEVELOPMENT.md) • [📖 API参考](docs/05_API.md)

</div>

## ✨ 特性

- 🚀 **简洁的 API** - 易于上手，快速开发
- 🔌 **插件系统** - 热插拔架构，模块化设计
- ⚙️ **灵活配置** - YAML + 环境变量支持
- 📝 **完善日志** - 按日期分隔，便于调试
- 🔄 **异步支持** - 高性能异步处理
- 🎯 **强类型事件** - 类型安全，减少错误
- 🧩 **事件总线** - 模块解耦，扩展灵活

## � 前置要求

RqhBot 基于 NapCat 的 OneBot11 协议通信，使用前需要先下载并配置 NapCat。

- 🔗 **NapCat 下载与安装指南**: [https://napneko.github.io/guide/napcat](https://napneko.github.io/guide/napcat)
- 📖 **NapCat 文档站**: [https://napneko.github.io/](https://napneko.github.io/)

请按照 NapCat 文档完成安装和基本配置，确保 NapCat 的 WebSocket 服务正常运行后再启动 RqhBot。

## �🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 NapCat 连接

编辑 `config.yaml` 文件：

```yaml
napcat:
  ws_url: "ws://localhost:3001"  # NapCat WebSocket 地址
  access_token: ""                # 访问令牌（如果有）
```

### 3. 启动机器人

```bash
python run.py
```

### 4. 测试机器人

在 QQ 群中发送：
- `测试` - 应该回复 "收到测试消息！"
- `hello` - 应该回复 "你好！"
- `help` - 显示可用命令列表

## 📁 项目结构

```
rqhbot/
├── sdk/                    # SDK 核心代码
│   ├── config/            # 配置管理模块
│   ├── core/              # 核心功能模块
│   └── pluginsystem/      # 插件系统模块
├── plugins/               # 插件目录
├── docs/                  # 文档目录
├── log/                   # 日志目录
├── config.yaml            # 配置文件
├── requirements.txt       # Python 依赖
└── run.py                 # 主入口文件
```

## 📚 文档导航

### 🚀 入门指南
- [项目概述](docs/02_OVERVIEW.md) - 了解 RqhBot
- [快速开始](docs/03_QUICK_START.md) - 5分钟上手
- [配置指南](docs/04_CONFIG_GUIDE.md) - 配置系统

### 💻 开发文档
- [API 参考](docs/05_API.md) - 完整 API
- [插件开发](docs/06_PLUGIN_DEVELOPMENT.md) - 开发指南（含速查表）

### 📖 完整文档
- [文档索引](docs/01_INDEX.md) - 所有文档入口

## 🎯 适用场景

- **个人机器人**: 群聊助手、私人助理、娱乐机器人
- **社群管理**: 自动回复、数据统计、内容审核
- **业务集成**: 消息推送、客户服务、自动化流程

## 🛠️ 技术栈

- **Python 3.8+**: 主要编程语言
- **websockets**: WebSocket 通信
- **aiohttp**: HTTP 客户端
- **PyYAML**: YAML 配置解析
- **python-dotenv**: 环境变量管理

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

---

<div align="center">

**版本**: 3.0.0 | **最后更新**: 2026-05-16

Made with ❤️ by RqhBot Team

</div>
