# 存款价值转换 (cunkuan-value-converter)

输入人民币金额，换算成 BTC、黄金、生活物资、股票与豪车等参考价值的开源 H5 + Python 小服务。

**在线演示：** [https://cunkuan.dpdns.org/](https://cunkuan.dpdns.org/)

> 演示站配置与本仓库默认值不同。Fork 后请按下方「配置」改成你自己的域名与密钥。

## 免责声明 / Disclaimer

本站仅供娱乐参考，不构成投资/消费建议；请勿用于任何违法用途；开源免费，禁止收费售卖。

For entertainment only. Not investment or purchase advice. Do not use for any illegal purpose. Free and open source — no paid resale.

补充说明：

- 本项目及演示站**仅供娱乐参考**，不构成任何投资、理财或消费建议。
- **请勿**将本站或本项目用于任何违法用途。
- **作者本人开源且不收费**；请勿将本站包装成收费服务欺骗用户。
- 本仓库按 [MIT](./LICENSE) 开源。若你基于本项目对外提供收费服务，须自行承担合规与用户告知责任，且**不得谎称官方**。

## 功能概览

- 静态前端：`index.html` + `styles.css` + `app.js`
- 轻量后端：`server.py`（行情聚合缓存、二维码、事件统计、管理页）
- 海报分享：页内生成结果图 + 二维码（`SHARE_URL`）+ Web Share API
- Open Graph：`assets/og.png`（1200×630）供微信/社交预览
- 可选统计：打开次数 / UV / 保存图片 / 分享 / 复制（见 [STATS.md](./STATS.md)）

## 本地运行

```bash
git clone https://github.com/manyin6/cunkuan-value-converter.git
cd cunkuan-value-converter
python3 server.py
```

打开 http://127.0.0.1:8765/

首次运行会自动在 `data/` 下创建空的 `stats.json` / `visitors.json`（已 gitignore，勿提交真实数据）。

### 管理后台（仅本地 / 受保护环境）

1. 打开 http://127.0.0.1:8765/admin
2. 在表单中输入 `ADMIN_KEY`（默认本地预览值 `deposit2026`）
3. POST `/api/admin/login` 写入 HttpOnly Cookie `admin_session`（约 12 小时）

也可用请求头访问 JSON：`Authorization: Bearer <ADMIN_KEY>` 或 `X-Admin-Key` → `/api/stats`。

**不要再把密钥写进 URL**（旧 `/admin?key=...` 会重定向到登录页，避免密钥进入访问日志）。

**默认 `ADMIN_KEY` 仅为方便本地预览。生产环境必须用环境变量覆盖为强随机值。**

## 配置

| 项 | 位置 | 默认（本仓库） | 说明 |
|----|------|----------------|------|
| `SHARE_URL` | `app.js` | `https://example.com/` | 海报二维码指向的公网 HTTPS 地址；fork 后务必改成你的域名 |
| `SHARE_SLOGAN` / `SHARE_QR_LABEL` | `app.js` | 中文口号 | 海报文案 |
| `ADMIN_KEY` | 环境变量 | `deposit2026` | 管理接口密钥；**上线务必更换** |
| `ALLOWED_ORIGINS` | 环境变量 | `https://example.com` | CORS 允许的 Origin，逗号分隔多个 |
| OG 图 | `assets/og.png` | 1200×630 | 改域名后请同步 `index.html` 里的 `og:url` / `og:image` |

示例：

```bash
export ADMIN_KEY="$(openssl rand -hex 24)"
export ALLOWED_ORIGINS="https://your.domain.example"
python3 server.py
```

## 部署要点

详见 [PROMOTE.md](./PROMOTE.md) 与 [HARDENING.md](./HARDENING.md) / [SECURITY.md](./SECURITY.md)。

简要建议：

1. 公网 **HTTPS**（Nginx / Caddy 反代到 `server.py`；转发 `X-Forwarded-Proto` 以便 Secure Cookie）
2. 设置强 `ADMIN_KEY` 与正确的 `ALLOWED_ORIGINS`
3. 用 Nginx **拒绝** 直接访问 `/.admin_key`、`/data/`、`/server.py`
4. 叠加网关限流（`/api/event`、`/api/qr`）
5. 改 `app.js` 里的 `SHARE_URL` 与 `index.html` OG 元数据后重新部署

## 安全

- **永远不要**把真实 `ADMIN_KEY`、`.admin_key`、`data/stats.json`、`data/visitors.json` 提交进 Git
- 完整清单见 [SECURITY.md](./SECURITY.md)

## 商标 / 素材说明

- UI 默认使用 **通用 SVG** 图标（见 `app.js` 的 `ART`）。
- `assets/brands/` 中的可选品牌 PNG **仅供演示**；商业用途请自行替换并确认商标合规。详见 [assets/brands/README.md](./assets/brands/README.md) 与 [SECURITY.md](./SECURITY.md)。

## 文档

| 文件 | 内容 |
|------|------|
| [HARDENING.md](./HARDENING.md) | 服务端加固与 Nginx 限流示例 |
| [SECURITY.md](./SECURITY.md) | 密钥、路径拒绝、CORS、轮换、商标 |
| [STATS.md](./STATS.md) | 统计口径 |
| [PROMOTE.md](./PROMOTE.md) | H5 推广与上线检查清单 |
| [WECHAT.md](./WECHAT.md) | 小程序路线（**已废弃 / 不随本仓库交付小程序**） |

## License

[MIT](./LICENSE) © 2026 manyin6

演示站由作者免费提供，仅供娱乐；请勿用于违法用途，亦请勿将本站包装成收费产品欺骗用户（详见上方「免责声明」）。

Demo site is free for entertainment only. Do not use illegally or resell as a paid product (see Disclaimer above).
