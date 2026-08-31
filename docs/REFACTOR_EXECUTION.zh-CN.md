# 重构执行记录

集成分支：refactor/plan。阶段子分支均从当时的集成分支创建，验收后 --no-ff 合并，保留分支，不修改 main、不 push。

## P1 — unified-config

- 根 .env 为唯一实际配置；.env.example 为无秘密模板。删除四份 backend/frontend test/production env，历史由 Git 保留。
- Settings 为唯一环境读取入口，进程覆盖文件，秘密值不进入 repr；保留原模型分层、名称和采样参数。
- 前端空 API base 改为同源，开发代理与网关共用；根 env 不进入镜像，浏览器只公开 API base。
- 8 项单测通过；前端 build 通过；基础及两个 override Compose 校验通过。
- 隔离 MySQL：用户创建/验证、会话、消息、health API 与 OpenAI 客户端初始化通过。
- 原本地 httpx 0.28 导致旧 OpenAI 的 proxies 参数异常；固定为兼容的 0.25.2，不涉及业务逻辑。
- 原报告最后一次修复不再校验的行为已用基线测试记录，本阶段未修改。
