# JiuwenClaw on OpenHarmony

> **懂你所想，自主演进**  
> 在鸿蒙设备上运行的 AI Agent 助手

[![HarmonyOS](https://img.shields.io/badge/HarmonyOS-NEXT%205.0-blue)](https://developer.huawei.com/consumer/cn/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

## 🌟 项目简介

**JiuwenClaw** 是一款运行在鸿蒙设备上的 AI Agent 应用。名字取意"久闻爪"——随叫随到的智能管家，像一只精准的爪子，随时准备为你服务。

### ✨ 核心特性

- **🧠 ReAct 推理循环** - 思考 + 行动，自主完成复杂任务
- **🔧 工具调用** - 文件操作、网页搜索、记忆管理、定时任务
- **💾 持久化记忆** - 跨会话记住你的偏好和重要信息
- **⏰ 定时任务** - 支持 cron、间隔、一次性任务
- **🌐 MCP 支持** - 可接入外部 MCP 服务器扩展能力
- **📚 RAG 知识检索** - 向量检索 + 关键词匹配

## 🚀 快速开始

### 1. 配置 API Key

首次使用需要在设置中配置 LLM API：

- **API Key**: 你的 DeepSeek / 其他 OpenAI 兼容 API Key
- **API 地址**: 默认 `https://api.deepseek.com/v1`
- **模型**: 默认 `deepseek-chat`

### 2. 开始对话

在聊天界面输入消息，JiuwenClaw 会：
1. 理解你的意图
2. 决定是否需要使用工具
3. 执行操作并返回结果

### 3. 快捷指令

点击输入框左侧的 ⚡ 按钮打开快捷指令面板：
- 🧹 清空对话
- 🧠 查看记忆
- 📁 文件列表
- ⏰ 定时任务
- 🔍 搜索新闻
- 📝 创建笔记

## 📱 功能演示

### 基础对话
```
你：介绍一下你自己
JiuwenClaw：我是 JiuwenClaw（久闻爪），一只运行在你鸿蒙设备上的 AI 助手...
```

### 文件操作
```
你：帮我创建一个 todo.md，写上今天要做的三件事
JiuwenClaw：[🔧 Using: file_write]
已创建 todo.md，内容包括...
```

### 记忆功能
```
你：记住我喜欢用中文回复
JiuwenClaw：[🔧 Using: memory_write]
已保存到记忆！以后我会默认用中文和你交流。
```

### 定时任务
```
你：每天早上9点提醒我喝水
JiuwenClaw：[🔧 Using: schedule_task]
任务已创建！每天 9:00 会提醒你喝水。
```

## 🏗️ 技术架构

```
┌──────────────────────────────────────────────┐
│  ArkUI 前端                                   │
│  ┌────────────┐    ┌────────────────┐        │
│  │ Index.ets  │    │ SettingsPage   │        │
│  │ 聊天界面    │    │ API/助手配置    │        │
│  └─────┬──────┘    └────────────────┘        │
│        │                                      │
│  ──────┼─────────── 服务层 ──────────────── │
│        │                                      │
│  ┌─────▼──────────────────────────────────┐  │
│  │  AgentCore.ets — ReAct 循环引擎        │  │
│  └────────────────────────────────────────┘  │
│       │          │           │                │
│  ┌────▼───┐ ┌───▼────┐ ┌───▼──────┐        │
│  │Database│ │Tool    │ │Task     │         │
│  │Service │ │Registry│ │Scheduler│         │
│  └────────┘ └───┬────┘ └──────────┘        │
│       ┌─────┬───┴───┬──────┐                 │
│    FileTools Memory WebTools TaskTools        │
└──────────────────────────────────────────────┘
```

### 文件结构

```
entry/src/main/ets/
├── common/
│   └── Types.ets          # 全局类型定义
├── services/
│   ├── AgentCore.ets      # ⭐ 核心：ReAct 循环引擎
│   ├── ApiClient.ets      # HTTP 客户端
│   ├── DatabaseService.ets# SQLite 数据库服务
│   ├── ConfigService.ets  # Preferences 配置管理
│   ├── ToolRegistry.ets   # 工具注册中心
│   └── TaskScheduler.ets  # 定时任务调度器
├── tools/
│   ├── FileTools.ets      # 文件读写列表
│   ├── MemoryTools.ets    # 持久化记忆
│   ├── WebTools.ets       # 网页抓取 + 搜索
│   └── TaskTools.ets      # 定时任务 CRUD
├── pages/
│   ├── Index.ets          # 聊天主界面
│   └── SettingsPage.ets   # 设置页面
└── entryability/
    └── EntryAbility.ets   # 应用生命周期
```

## 🛠️ 开发环境

- **DevEco Studio** 最新版本
- **HarmonyOS NEXT** 5.0.5 (API 17)
- **ArkTS** (TypeScript 严格子集)

## 📖 参考资料

- [JiuwenClaw](https://openjiuwen.com/jiuwenclaw) - 原版 Python 实现
- [NanoClaw](https://github.com/lmxxf/openclaw-on-openharmony) - 架构参考
- [HarmonyOS 开发文档](https://developer.huawei.com/consumer/cn/)

## 📄 开源协议

本项目采用 **Apache License 2.0** 开源协议。

---

<p align="center">
  <strong>🐾 JiuwenClaw —— 懂你所想，自主演进 🐾</strong>
</p>
