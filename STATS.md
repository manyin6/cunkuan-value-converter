# 统计口径说明（STATS）

时区一律 **Asia/Shanghai**。数据文件：`data/stats.json`（计数）、`data/visitors.json`（访客哈希列表）。这些文件由服务首次运行时自动创建，**不要提交进 Git**。

| 指标 | 含义 | 如何计入 |
|------|------|----------|
| **打开次数 (PV)** | 页面打开次数 | 前端每个浏览器**会话**只上报 1 次 `view`；`?sharepreview` 不上报；`document.hidden` 时不报 view |
| **独立访客 (UV)** | 去重访客数 | 客户端 `localStorage` 访客 ID → 服务端 SHA256 截断；**新 ID 才 +1**；计数永久递增，不因列表截断回退 |
| **保存图片** | 海报下载成功 | 仅走下载保存路径时 `save_image`；**系统分享成功不计入此项** |
| **系统分享** | 调起系统分享并成功 | Web Share API resolve 后只记 `share`；用户取消（AbortError）不记 |
| **复制结果** | 复制成功 | 剪贴板写入成功后记 `copy` |

## 防刷与过滤

- 客户端：同事件类型 **2 秒**内防抖；无访客 ID 不上报
- 服务端：同 `(访客哈希, 事件类型)` **2 秒**内忽略重复
- 仅对 `view`：User-Agent 匹配 bot/spider/crawl/slurp/facebookexternalhit/preview/HeadlessChrome/wget/curl/python-requests 则忽略（不挡 `/api/prices`）
- 必须带 `type` 与 `vid`，否则 400

## 管理入口

- 页面：`/admin?key=ADMIN_KEY`（默认本地预览值为 `deposit2026`，**生产务必用环境变量覆盖**）
- JSON：`/api/stats?key=...`

**不要**把真实 `stats.json` / `visitors.json` 提交到公开仓库；生产环境清空统计前请先备份。
