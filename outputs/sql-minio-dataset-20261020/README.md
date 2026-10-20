# PostgreSQL + MinIO 数据交付

本包包含一个 PostgreSQL 17 SQL 文件、339 张图片和首次上传脚本。无需旧采集目录。
SQL 在独立的 `collected_data` schema 中建表，不改现有业务表，不创建真实租约、租户或维修工单。
导入后可直接查询，但不会自动出现在现有应用页面；应用需读取这些表或做后续映射。

## 数据

- 学生公寓：29 条，81 张独立图片，82 个图片关联。
- 社会房源：29 条，183 张图片。
- 维修：59 条，75 张图片，非真实工单。
- 知识文档：11 篇英文正文，62 个教程步骤。
- 藻斑不包含在图片中。未知信息保留空值，历史与待核验状态保存在 metadata。

## 使用方法

如果目标 MinIO 中已完成图片上传，只需导入 SQL，再配置应用的 MinIO 连接。
若使用各自的 MinIO，需先上传图片。SQL 不会连接 MinIO，不会验证对象已存在。

### 1. 首次上传图片

在解压目录打开终端，Python 3.11+：

```powershell
python -m pip install -r requirements.txt
python upload_images.py
# 上一条只校验本地文件，不联网。

$env:MINIO_ENDPOINT = "localhost:9000"
$env:MINIO_SECURE = "false"
# 在自己的终端安全设置 MINIO_ACCESS_KEY、MINIO_SECRET_KEY，不提交到仓库。
python upload_images.py --upload
# 桶不存在且当前账号有建桶权限时，可加 --create-bucket。
```

生产或远程 HTTPS 连接设置 `MINIO_SECURE=true`，脚本默认使用 HTTPS。
项目容器内部默认地址 `gateway:9000` 不能直接当作宿主机地址；
请根据实际网关端口映射设置可达地址。脚本读取环境变量，不自动读取 `.env`。

对象位置固定为：

```text
bucket: safescan-media
object_key: datasets/collection-20261009/images/<SHA256>.<扩展名>
```

SQL 和上传清单共享同一索引，不提供会导致两者不一致的桶名覆盖参数。
使用现有私有桶，不修改桶策略、不设为公开。读取图片时由应用使用 MinIO SDK 获取对象或临时生成签名链接。
重复执行会校验已有对象内容并跳过；内容不同则停止，不覆盖。中途中断可重跑。

### 2. 导入 SQL

需要能创建 schema 和表的 PostgreSQL 账号。使用自己的连接配置，不把密码放在 SQL 中。

```powershell
# PGHOST、PGPORT、PGUSER、PGDATABASE 及认证方式按本机数据库配置。
psql -v ON_ERROR_STOP=1 -f dataset.sql
```

也可在 DBeaver/pgAdmin 的 PostgreSQL SQL 编辑器中执行完整文件。
SQL 使用单一事务，失败需回滚后处理错误。请在独立测试数据库中首次导入。
重复导入按主键更新，不清空表、不删除自建数据；这不是清理旧版本的迁移脚本。

### 3. 查询

```sql
SELECT h.id, h.name, h.city, a.bucket, a.object_key, hm.role
FROM collected_data.housing_records h
JOIN collected_data.housing_media hm ON hm.housing_id = h.id
JOIN collected_data.media_assets a ON a.id = hm.media_id
WHERE h.dataset_type = 'student';

SELECT r.name, r.category, a.bucket, a.object_key
FROM collected_data.repair_cases r
JOIN collected_data.repair_media rm ON rm.repair_id = r.id
JOIN collected_data.media_assets a ON a.id = rm.media_id;

SELECT id, title_zh, body FROM collected_data.knowledge_documents;
SELECT step_number, title, body FROM collected_data.knowledge_steps
WHERE document_id = '105443' ORDER BY step_number;
```

## 文件与验证

- dataset.sql：建表、数据、索引，UTF-8 编码。文档正文在数据库中。
- objects/：待上传的实际图片；objects.json：上传清单，含哈希、桶、对象键。
- upload_images.py：默认只做本地校验，传入 --upload 才写 MinIO。
- summary.json：数量；manifest.json：文件校验清单。

图片索引的权威路径是 `bucket + object_key`，metadata 中保留的旧本地路径只是溯源信息，不用于读取。
原来源许可和适用范围保留，不代表已取得再发布授权，也不构成维修指导或当前法律规则核验。
本次未对正在运行的 PostgreSQL/MinIO 执行导入；实际联机验证情况以交付时说明为准。
