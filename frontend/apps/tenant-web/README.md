# SafeScan Tenant / Prospect Portal P0

React 19 + TypeScript SPA，部署基路径为 `/tenant/`。默认启用集中式 mock adapter；在 URL 增加
`?api=real` 可切换至同源真实 BFF。浏览器业务请求只访问 `/api/v1/tenant/*`；注册、登录、刷新与
退出按契约访问 Gateway 直达的 `/api/v1/auth/*`。

## 本地演示

```sh
cd frontend
npx vite apps/tenant-web --base=/tenant/ --host 127.0.0.1 --port 4173
```

打开 `http://127.0.0.1:4173/tenant/`。顶部“演示身份”可切换 Guest、Prospect、executed Tenant、
active Tenant 和 Former Tenant。Mock 登录邮箱包含 `prospect`、`executed`、`active` 或 `former`
即可进入对应投影。

## 权限原则

- 菜单和操作只消费 bootstrap 返回的 capability，不从表单、URL 或本地业务状态推断 Tenant。
- executed Tenant 只有合同、待入住房产和缴费读取；维修与报告在 active 后才开放。
- Former Tenant 只能从历史 Lease 房产入口读取同一 `source_lease_id` 的合同与报告。
- 报告创建请求不提交 subject、property 或 lease ID；BFF 从唯一 active Lease 推导。
- Agent 仅为导航占位。

## 验证

```sh
npm run typecheck
npm run lint
npm test
npm run build:tenant
```
