<p align="center">
  <img src="https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690b6.svg" width="120" alt="Gemini2API">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Async-httpx-ff6b35?style=flat-square&logo=python&logoColor=white" alt="httpx">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/License-MIT-orange?style=flat-square" alt="License">
</p>

<h1 align="center">Gemini2API</h1>

<p align="center">
  轻量级 Gemini Web 反向代理，一套代码兼容三大主流 AI SDK<br/>
  纯异步架构 · 零官方 Key · 30 秒 Docker 部署
</p>

> [!NOTE]
> 本项目仅供个人学习与研究用途。

> [!WARNING]
> 通过浏览器 Cookie 调用 Gemini 可能违反其服务条款，风险自负。

---

## 🎯 为什么选择 Gemini2API

| | Gemini2API | 同类方案 |
|--|-----------|---------|
| 语言 | Python 3.12（易读易扩展） | Go（修改门槛高） |
| 架构 | 纯 async/await，天然高并发 | 同步 + goroutine |
| 数据校验 | Pydantic 自动校验请求/响应 | 手动 struct 解析 |
| 扩展性 | FastAPI 路由插件式开发，加功能只需新增一个文件 | 需要理解 DI 框架 |
| 部署体积 | ~60MB 镜像（slim base） | ~20MB（Go 二进制） |
| 开发效率 | 热重载，改完即生效 | 需编译 |

**核心优势**：
- **三合一兼容** — 一个服务同时提供 OpenAI、Claude、Gemini 三种 SDK 格式，切换零成本
- **全异步链路** — 从 HTTP 接收到 Gemini 请求全程 async，不阻塞任何连接
- **Pydantic 强类型** — 请求参数自动校验，不再因字段缺失导致 500
- **模块化设计** — 每个 API 格式独立路由文件，新增功能不影响现有代码
- **Cookie 自愈** — 自动轮换 + 定时刷新，无需手动维护会话

---

## ✨ 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| OpenAI 兼容 API | ✅ | `/openai/v1/chat/completions`，支持流式 |
| Claude 兼容 API | ✅ | `/claude/v1/messages`，完整 SSE 协议 |
| Gemini 原生 API | ✅ | `/gemini/v1beta/models/:model:generateContent` |
| Function Calling | ✅ | 三种格式均支持工具调用 |
| 流式响应 | ✅ | SSE（OpenAI/Claude）+ Chunked JSON（Gemini） |
| Deep Research | ✅ | 多步骤深度研究，支持同步/流式/异步 |
| Cookie 自动刷新 | ✅ | 后台定时轮换，无感续期 |
| 模型自动发现 | ✅ | 启动时从 Web 页面提取可用模型列表 |
| 速率限制 | ✅ | 可选，基于 IP 的滑动窗口限流 |
| 健康检查 | ✅ | `/health` 端点，适配 Docker 健康探针 |

---

## ⚡ 快速部署

### 1. 获取 Cookie

1. 浏览器访问 [gemini.google.com](https://gemini.google.com) 并登录
2. F12 打开开发者工具 → Application → Cookies → `gemini.google.com`
3. 找到并复制 `__Secure-1PSID` 和 `__Secure-1PSIDTS`

### 2. Docker 一键启动

```bash
git clone https://github.com/xwteam/gemini2api.git
cd gemini2api

cp .env.example .env
# 编辑 .env，填入上一步获取的 Cookie 值

docker compose up -d
```

### 3. 验证服务

```bash
curl http://localhost:4981/health
# {"status":"ok","service":"gemini2api"}

curl http://localhost:4981/openai/v1/models
# 返回可用模型列表
```

---

## 🛠️ 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `GEMINI_PSID` | ✅ | — | 浏览器 `__Secure-1PSID` |
| `GEMINI_PSIDTS` | ❌ | — | 浏览器 `__Secure-1PSIDTS`（可自动获取） |
| `REFRESH_INTERVAL` | ❌ | `5` | Cookie 刷新周期（分钟） |
| `MAX_RETRIES` | ❌ | `3` | 失败重试次数（指数退避） |
| `PORT` | ❌ | `4981` | 服务端口 |
| `LOG_LEVEL` | ❌ | `info` | 日志级别（debug/info/warning/error） |
| `RATE_LIMIT_ENABLED` | ❌ | `false` | 启用限流 |
| `RATE_LIMIT_WINDOW` | ❌ | `60` | 限流窗口（秒） |
| `RATE_LIMIT_MAX` | ❌ | `10` | 窗口内最大请求数 |

---

## 🧪 接入示例

### OpenAI SDK（Python）

```python
from openai import OpenAI

client = OpenAI(
    api_key="any-string",
    base_url="http://localhost:4981/openai/v1"
)

for chunk in client.chat.completions.create(
    model="gemini-2.0-flash",
    messages=[{"role": "user", "content": "用三句话解释相对论"}],
    stream=True
):
    print(chunk.choices[0].delta.content or "", end="")
```

### Claude SDK（Python）

```python
import anthropic

client = anthropic.Anthropic(
    api_key="any-string",
    base_url="http://localhost:4981/claude"
)

msg = client.messages.create(
    model="gemini-2.0-flash",
    max_tokens=4096,
    messages=[{"role": "user", "content": "写一个快速排序的Python实现"}]
)
print(msg.content[0].text)
```

### cURL

```bash
# 非流式请求
curl -X POST http://localhost:4981/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.0-flash","messages":[{"role":"user","content":"Hi"}]}'

# 流式请求
curl -X POST http://localhost:4981/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.0-flash","messages":[{"role":"user","content":"Hi"}],"stream":true}'
```

### Function Calling

```python
response = client.chat.completions.create(
    model="gemini-2.0-flash",
    messages=[{"role": "user", "content": "北京今天天气怎么样"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            }
        }
    }]
)
```

---

## 📘 API 端点一览

### OpenAI 兼容（`/openai/v1`）

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/models` | 可用模型列表 |
| POST | `/chat/completions` | 对话补全（支持流式 + 工具调用） |

### Claude 兼容（`/claude/v1`）

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/models` | 模型列表 |
| GET | `/models/{id}` | 模型详情 |
| POST | `/messages` | 消息生成（支持流式 + 工具调用） |
| POST | `/messages/count_tokens` | Token 计数估算 |

### Gemini 原生（`/gemini/v1beta`）

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/models` | 模型列表 |
| POST | `/models/{m}:generateContent` | 内容生成 |
| POST | `/models/{m}:streamGenerateContent` | 流式生成（Chunked JSON） |

### Deep Research（`/gemini/v1beta/deepresearch`）

| 方法 | 端点 | 功能 |
|------|------|------|
| POST | `/` | 同步深度研究（规划→调研→综合报告） |
| POST | `/stream` | 流式研究（实时进度推送） |
| POST | `/interact` | 异步任务模式（创建→轮询结果） |

### 系统

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | `/health` | 健康检查（Docker 探针适配） |

---

## 🏗️ 项目结构

```
gemini2api/
├── app/
│   ├── main.py                 # 应用入口，中间件注册
│   ├── config.py               # Pydantic 配置管理
│   ├── core/
│   │   ├── gemini_client.py    # Gemini Web 核心客户端
│   │   └── stream.py           # 流式工具函数
│   ├── models/                 # Pydantic 数据模型
│   │   ├── openai.py
│   │   ├── claude.py
│   │   └── gemini.py
│   ├── routers/                # API 路由（每种格式独立）
│   │   ├── openai.py
│   │   ├── claude.py
│   │   ├── gemini.py
│   │   └── research.py
│   └── utils/                  # 工具函数
│       ├── tools.py            # Function Calling 桥接
│       └── prompt.py           # 消息格式化
├── Dockerfile                  # 多阶段构建
├── docker-compose.yml          # 编排配置
├── requirements.txt
└── .env.example
```

---

## 🗺️ 开发路线

- [x] OpenAI / Claude / Gemini 三格式兼容
- [x] 流式响应 + Function Calling
- [x] Deep Research 深度研究
- [x] Docker 部署
- [ ] 多账号轮询（负载均衡）
- [ ] Web 管理面板
- [ ] 对话上下文持久化
- [ ] 图片/文件上传支持
- [ ] Prometheus 监控指标

---

## 🤝 贡献

欢迎 PR 和 Issue。

1. Fork 本仓库
2. 创建分支 `git checkout -b feature/your-feature`
3. 提交代码 `git commit -m "feat: add something"`
4. 推送并创建 Pull Request

---

## 📄 License

[MIT](LICENSE)

---

<p align="center">Made with ❤️ by xwteam</p>
