# 安全加固说明

配套文档：[SECURITY.md](./SECURITY.md)

## 已做（server.py）

1. **`/api/event` 限流（进程内）**  
   - 每 IP：最多 **30 事件/分钟**；其中 `view` 另限 **10 次/分钟**。  
   - IP 取自 `X-Forwarded-For` **最左一跳**（需 Nginx 正确设置），否则用直连 `client_address`。  
   - CORS：仅允许 `ALLOWED_ORIGINS`（默认占位 `https://example.com`；无 Origin 的同源请求放行）；其它 Origin 的 POST/OPTIONS 拒绝。  
   - 软校验：若带 Referer/Origin 且不匹配站点则 403。

2. **`/api/prices`**  
   - 公开请求的 `refresh=1` / `force=1` **忽略**（不打上游）。  
   - 仅 `?key=ADMIN_KEY&refresh=1` 可强制刷新。  
   - `gather_prices()` 在 **释放 cache 锁之后** 执行，避免锁 convoy。

3. **`/api/qr`**  
   - 数据长度上限 2048。  
   - 每 IP **20 次/分钟**。

4. **安全响应头**  
   - `X-Content-Type-Options: nosniff`  
   - `Referrer-Policy: strict-origin-when-cross-origin`  
   - `X-Frame-Options: DENY`  
   - HTML：基础 `Content-Security-Policy`

5. **统计文件**  
   - `data/` 目录在首次运行时自动创建；缺失的 `stats.json` 按空模板初始化。  
   - **不要**把真实统计文件提交进 Git。

前端刷新行情应只读缓存 `/api/prices`（不要对公网开放 `refresh=1`）。

## 生产必做

- 设置强随机 `ADMIN_KEY` 环境变量  
- 设置 `ALLOWED_ORIGINS` 为你的 HTTPS 站点  
- 修改 `app.js` 中 `SHARE_URL`  
- Nginx **deny** `/.admin_key`、`/data/`、`/server.py`（见 SECURITY.md）  
- 叠加网关限流（下面示例）

## Nginx 建议（与进程内限流叠加）

```nginx
# 信任一层反代时写入真实客户端 IP
# set_real_ip_from ...;
# real_ip_header X-Forwarded-For;

limit_req_zone $binary_remote_addr zone=dvc_event:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=dvc_qr:10m rate=20r/m;

location /api/event {
    limit_req zone=dvc_event burst=10 nodelay;
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Real-IP $remote_addr;
}

location /api/qr {
    limit_req zone=dvc_qr burst=5 nodelay;
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location /api/prices {
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location ~ /\.admin_key { deny all; return 404; }
location ^~ /data/ { deny all; return 404; }
location = /server.py { deny all; return 404; }
```

多 worker / 多机时必须以 Nginx（或网关）限流为准；进程内桶仅单进程有效。
