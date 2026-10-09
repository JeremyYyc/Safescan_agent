# UniLodge 本地采集预览

2026-09-29 补采，独立于之前冻结的选型样例，不覆盖历史快照。

## 打开位置

使用浏览器打开本地文件：

`D:\project\Safescan_agent\data\collection-pilot\unilodge-20260929-v2\preview.html`

无需启动服务；图片使用同目录 `media/raw` 下的文件。房型来源、原图来源和 VR 链接才会跳转外部网站。移动整个结果时应保留完整目录，不能只移动 HTML。

## 本轮范围

- 固定抓取 UniLodge Melbourne Flagstaff 楼盘页、条款页、Studio/两卧/四卧三个详情页，另检查 robots。
- 提取 5 个目标房型。不是全站抓取，也不是 5 个具体房号。
- 当前快照只有 2 个房型带报价，共 4 条。历史快照的 7 条报价不补入本次结果。
- 下载 17 个房型图库文件及 4 个标签匹配的完整布局图候选；21/21 下载成功，21 个不同内容 hash。
- 4 个 Matterport 入口，没有下载视频文件。

图库按房型分组，已知图片复用按 hash 绑定的助手审核标签，新图片保留待分类状态。未独立人工审核的媒体不能标记为合格实况图。楼盘页的 Studio Deluxe Queen 不直接当作 Studio Queen 的确定图纸，只展示房型页自身关联的图片。

面积保留 studio/单间卧室口径，币种及不明确的计价对象仍待确认；页面默认日期不是签署合同。图库有样板间/示意性质，内容复用权限未知，未发布或导入业务数据库。

## 复现

已有快照离线重建预览：

```powershell
python -X utf8 scripts/data_collection/unilodge_preview.py --source data/collection-pilot/unilodge-20260929-v2 --media data/collection-pilot/unilodge-20260929-v2/media
python -m unittest discover -s scripts/data_collection -p "test_*.py"
```

`--fetch` 会执行有上限的新媒体请求，要求媒体输出目录不存在；离线重建不要加该参数。HTML 仅展示已下载图片，图片点击打开本地原始文件，不修改原图。

追溯文件：`pages.json`、`run.json`、`room_types.json`、`media/outcomes.json`、`media/manifest.json`、`preview_media.json`、`preview_summary.json`、`preview_manifest.json`。
