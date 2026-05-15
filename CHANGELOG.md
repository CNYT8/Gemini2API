# Changelog

本文件记录项目的所有重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [Unreleased]

## [0.2.0] - 2025-05-15

### Added
- 账号状态定时检测功能，支持自定义检测间隔
- 健康检查历史记录 API（`GET /admin/health-history`）
- Cookie 热更新接口（`POST /admin/reload-cookies`），无需重启即可刷新凭证
- 账号状态实时检测接口（`GET /admin/check-account`）
- 连续失败自动标记不健康机制

### Changed
- 许可协议变更为 PolyForm Noncommercial 1.0.0

## [0.1.0] - 2025-05-14

### Added
- Deep Research 深度研究功能
- OpenAI / Claude / Gemini 三格式函数调用支持
- SSE 流式输出（OpenAI / Claude）+ Chunked JSON（Gemini）
- API Key 自动生成与认证（`sk-` 前缀）
- Cookie 后台自动刷新，无感续期
- Docker 一键部署
- 速率限制（可选）
- 完整的管理接口（`/admin`）

## [0.0.1] - 2025-05-13

### Added
- 项目初始化
- 基础 Gemini Web 反向代理功能
- FastAPI + httpx 异步架构搭建
- Pydantic 配置管理与数据模型
