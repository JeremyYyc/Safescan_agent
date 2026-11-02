# Property Manager 与合同 PDF 修复（2026-11-02）

本次分支：`codex/property-manager-contract-pdfs`，基于 `6ddac4a`。

## 图片回退修复

后续发现原本运行环境的图片功能位于另一未合并工作目录，按本分支重建时没有带入：两端图片字段映射缺失，Property/BFF 图片路由返回 404。MinIO 原图片文件仍完好。

已将图片读取和两端代理纳入本分支。租户图片先验证房源正在公开招租，员工图片先验证房源 scope；仅读取该房源 `marketing_media` 白名单中的对象，允许常见位图类型，并从返回的房源属性中移除内部 bucket/object_key 元数据。员工端使用 Bearer 请求和可释放的 Blob URL，租户端使用公开房源图片路径；缺图保留占位。

验收：员工 BFF 31、租户 BFF 13、房源相关 30 项测试通过；前端图片映射及 Bearer/外站拒绝回归通过。实际租户 PNG 与员工 JPEG 返回 200、对应字节正常；员工无凭证为 401。浏览器确认租户可见照片解码正常，当前员工空置列表 16 张照片全部解码显示。两端构建、类型及 lint 检查通过。

## 行为变化

- 维修列表把逐房源 token exchange / 授权改为一页一次批量授权；Property 服务用单条 SQL 检查实时房源、楼宇 scope 及有效期。BFF 用两个有界批量投影补全房源与负责人姓名，辅助服务失败时保留工单及游标并返回 `partial_errors`。
- 员工端恢复维修状态筛选、每页 50 条、前后翻页，允许继续翻过当前授权扫描结果为空的页。分派仍走独立分派接口。
- Property Manager 侧栏分为“空置房源”和“在租与待入住”；房源与订单完整加载游标分页，避免只显示首 20 条。房源投影增加当前租约，支持直接查看合同。
- 个人资料按实际授权楼宇地址及地区时区显示掌管州，楼宇详情可展开；加载失败明确显示暂不可用。
- 员工订单、Property Manager 房源、租户当前和历史合同支持认证 PDF 预览、新窗口打开。关闭预览释放 Blob URL，弹窗支持键盘和焦点管理。

## PDF 来源和数据边界

使用各州完整官方范本，不自行编造法定条款：

| 地区 | 官方来源 | 固定附件 |
|---|---|---|
| NSW | [NSW Fair Trading](https://www.nsw.gov.au/housing-and-construction/rental-forms-surveys-and-data/resources/standard-residential-tenancy-agreement) | 2026-09-21 版，20 页 |
| VIC | [Consumer Affairs Victoria](https://www.consumer.vic.gov.au/housing/renting/starting-and-changing-rental-agreements/different-rental-agreements/residential-rental-agreements) | Form 1 官方 DOCX 转 PDF，10 页 |
| QLD | [Residential Tenancies Authority](https://www.rta.qld.gov.au/forms-resources/forms/forms-for-general-tenancies/general-tenancy-agreement-form-18a) | Form 18a v23 Sep25，12 页 |
| SA | [Consumer and Business Services](https://www.sa.gov.au/topics/housing/renting-and-letting/renting-privately/start-of-tenancy/Lease-agreements) | 官方固定期限租约，5 页 |
| WA | [Consumer Protection WA](https://www.consumerprotection.wa.gov.au/publications/rent-agreement-form-1aa) | Form 1AA March 2026 DOCX 转 PDF，11 页 |

原件、转换件、下载日期及 SHA-256 记录于 `backend/services/property-leasing-service/app/resources/lease_templates/sources.json`。WA 已使用官网现行 DOCX，旧 PDF 地址不可用。

每份 PDF 先显示该租约真实存储的租户、房源、租金、租期及补充字段，再附完整对应州范本。NSW、QLD、SA 的可识别原生表单字段填入已知值，并核验字段树、控件值和外观一致；VIC、WA 的转换件没有 PDF 表单字段，对应数据在前面的记录页显示。中文使用开源 Droid Sans Fallback 字体子集嵌入，来源与 Apache 2.0 许可证随资源保存。

当前 1,880 份记录均为数据库标记的模拟数据，PDF 明确标注 demonstration data。缺失的出租方、押金、收款方式等保留为未提供。原签约文档 UUID、`terms_payload`、`terms_digest` 和签名事件不变；不生成手写签名，也不把数据库展示副本声称为已签署原件。

## 存储和运行

私有对象位于根环境 `MINIO_REPORTS_BUCKET`：

```text
lease-contracts/{lease_uuid}/{document_uuid}/v{document_version}-{fingerprint}.pdf
```

fingerprint 包含渲染版本、完整记录及官方范本内容。状态、签名或条款变化会生成对应新对象，不覆盖旧版本。生成过程使用内存流，不将业务 PDF 写入应用目录。API 和 worker 均通过 `gateway:9000` 访问 MinIO。

默认部署不自动生成或同步合同文件。`property-leasing-document-worker` 已移入显式 `data-sync` profile，常规
`docker compose up` 不启动它。首次认证下载仍可按需生成缺失对象。手动一次回填统一使用：

```sh
python scripts/data/sync.py --steps lease-pdf --dry-run
python scripts/data/sync.py --steps lease-pdf --apply
```

浏览器读取路径：

```text
GET /api/v1/staff/leases/{lease_id}/document/pdf
GET /api/v1/tenant/leases/{lease_id}/document/pdf
```

先验证租约权限再读取 MinIO，包含缓存命中；返回 PDF 字节，响应 `private, no-store`，不向浏览器暴露对象密钥或公开存储链接。现有用于签约的 JSON 文档接口保持兼容。

## 验证

- Maintenance 在独立迁移后的 PostgreSQL 临时库：45 项通过。
- Property 在独立迁移后的 PostgreSQL 临时库：51 项通过；后续新增房源投影及最终渲染调整另有离线回归。
- Identity 合同及员工姓名投影：37 项通过；Staff BFF：30 项通过；Tenant BFF：12 项通过。
- 真实本机 Gateway：8 个员工账号、545 页维修列表，均 200、无重复、无 scope 泄漏；跨 PM 和跨维修员读取仍 404。Noah 修复前 1208ms / 504，批量授权修复后首次 55ms / 200；补齐展示投影后热请求约几十毫秒。
- 五州实际租约 PDF 全部渲染检查，表单中文姓名与字段完整可见。
- 员工端 40 项、租户端 21 项测试通过；两端 lint、类型检查、生产构建及共享组件 lint 通过。补充生产 JSX 编译和实际渲染测试，覆盖共享组件位于应用根目录外时的运行错误。
- 浏览器实际点击合同，确认认证 PDF 内嵌预览成功；状态筛选、第二页工单、房源姓名投影及管理地区显示正常。

最终只读验收 `complete: true`：1880 / 1880 份通过，缺文档租约 0，失败 0，总文件字节 1,031,823,544。覆盖 NSW 427、VIC 550、QLD 487、SA 292、WA 124 份；包含历史已结束租约 1461、在租 339、已执行待入住 80。每份为两张记录页加完整官方范本。结构化结果见同目录 `lease-pdf-storage-audit-20261102.json`。

此前后台 watch 的幂等验收输出为 `scanned=1880, generated=0, existing=1880, failed=0`。按后续“数据仅手动同步”要求，
watch 已停止，默认不启用。只有明确运行 `docker compose --profile data-sync up -d property-leasing-document-worker`
才会开启持续扫描。员工、业务导入、媒体、城市分配、合同生成的统一入口及顺序见
[`scripts/data/README.md`](../../../scripts/data/README.md)。本机此次使用 `safescan-pm-*:20261102` 镜像，沿用现有根环境文件与数据卷，仅更新相关应用服务。

只读全量存储验收（不会补文件或修改业务数据）：

```sh
docker compose exec -T property-leasing-service python - \
  --expected-leases 1880 --expected-documents 1880 \
  < scripts/ci/verify-lease-pdf-storage.py
```

该检查计算当前精确对象键，逐份验证类型、合同元数据、完整文件 SHA-256、PDF 结构及页数，并检查有无缺合同文档的租约；仅 `complete: true` 表示全量验收通过。临时集成测试数据库已删除，未在日常业务库运行集成测试。
