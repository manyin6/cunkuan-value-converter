/**
 * 存款价值转换
 * Retail baselines offline; live BTC/GOLD/TSLA/AAPL via /api/prices.
 */

/** Editable share branding */
const SHARE_URL = "https://example.com/";  // forks: set to your public HTTPS origin
const SHARE_SLOGAN = "算算你的存款能换什么 · 存款价值转换";
const SHARE_QR_LABEL = "长按扫码 · 算算你的存款";

/** Poster shows this curated set (page shows all ITEMS) */

/** Analytics */
const TRACK_DEBOUNCE_MS = 2000;
const _lastTrackAt = Object.create(null);

function isSharePreview() {
  try {
    return new URLSearchParams(location.search).has("sharepreview");
  } catch {
    return false;
  }
}

function getVisitorId() {
  try {
    const k = "dvc_vid";
    let v = localStorage.getItem(k);
    if (!v) {
      v = "v_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(k, v);
    }
    return v;
  } catch {
    return null;
  }
}

function track(type) {
  if (isSharePreview()) return;
  const allowed = { view: 1, save_image: 1, copy: 1, share: 1 };
  if (!allowed[type]) return;

  const now = Date.now();
  if (_lastTrackAt[type] && now - _lastTrackAt[type] < TRACK_DEBOUNCE_MS) return;
  _lastTrackAt[type] = now;

  const vid = getVisitorId();
  if (!vid) return;

  const body = JSON.stringify({ type, vid });
  // Prefer fetch+JSON for reliable Content-Type; beacon as fallback
  try {
    fetch("/api/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {
      try {
        if (navigator.sendBeacon) {
          navigator.sendBeacon("/api/event", new Blob([body], { type: "application/json" }));
        }
      } catch (_) {}
    });
  } catch (_) {
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/event", new Blob([body], { type: "application/json" }));
      }
    } catch (_) {}
  }
}

const SHARE_ITEM_IDS = [
  "btc", "gold", "mantou", "beef", "moutai", "iphone", "macbook", "luckin",
  "tsla", "aapl", "beijing", "gas", "maybach", "ferrari",
];

const BASELINE = {
  USD_CNY: 6.7034,
  BTC_CNY: 560939.99,
  GOLD_CNY: 926.5,      // AU9999 mid ~2026-09-26
  TSLA_CNY: 2374.55,
  AAPL_CNY: 2215.47,
  mantou: 1.5,
  beef: 71.59,
  fridge: 4000,
  washer: 3500,
  ac: 2150,
  maybach: 1398000,
  ferrari: 2418000,
  moutai: 1800,         // 飞天茅台 53度500ml · 市场终端均价参考（约1800元/瓶，2026-09）
  iphone: 10999,        // iPhone 18 Pro Max 256GB 国行官网
  macbook: 8499,        // MacBook Air 13" M5 国行起售
  luckin: 18,           // 瑞幸拿铁日常到手价量级
  gas92: 8.29,          // 北京 92# 元/升
  beijing_m2: 37142,    // 北京二手房均价 元/㎡ ~2026-09
  asOf: "2026-09-30",
  timezone: "Asia/Shanghai",
};

const prices = {
  BTC_CNY: BASELINE.BTC_CNY,
  GOLD_CNY: BASELINE.GOLD_CNY,
  TSLA_CNY: BASELINE.TSLA_CNY,
  AAPL_CNY: BASELINE.AAPL_CNY,
  USD_CNY: BASELINE.USD_CNY,
  live: { btc: false, gold: false, tsla: false, aapl: false },
  sources: {},
  fetchedAt: null,
};

/** Object-like / brand emblem SVGs */
const ART = {
  btc: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><circle cx="32" cy="32" r="28" fill="#F7931A"/><path fill="#fff" d="M36.8 28.4c.5-3.4-2.1-5.2-5.6-6.4l1.1-4.6-2.8-.7-1.1 4.5c-.7-.2-1.5-.3-2.2-.5l1.1-4.5-2.8-.7-1.1 4.6c-.6-.1-1.2-.3-1.8-.4l-3.8-.9-.7 3s2.1.5 2 .5c1.1.3 1.3 1 1.3 1.6l-1.3 5.3c.1 0 .2.1.3.1h-.3l-1.8 7.3c-.1.4-.5.9-1.2.7 0 0-2-.5-2-.5l-1.4 3.5 3.6.9c.7.2 1.3.3 2 .5l-1.2 4.7 2.8.7 1.1-4.6c.8.2 1.5.4 2.2.5l-1.1 4.5 2.8.7 1.2-4.7c4.8.9 8.4.5 9.9-3.8 1.2-3.5-.1-5.5-2.5-6.8 1.8-.4 3.1-1.6 3.5-4.1zm-6.2 9.1c-.9 3.5-6.7 1.6-8.6 1.1l1.5-6.2c1.9.5 7.9 1.4 7.1 5.1zm.9-9.2c-.8 3.2-5.7 1.6-7.3 1.2l1.4-5.6c1.6.4 6.8 1.1 5.9 4.4z"/></svg>`,


  gold: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="8" y="18" width="48" height="32" rx="3" fill="#D4A017"/><rect x="10" y="20" width="44" height="28" rx="2" fill="#F0C14B"/><rect x="14" y="24" width="36" height="20" rx="1.5" fill="#C9960A"/><text x="32" y="37" text-anchor="middle" fill="#FFF8DC" font-size="9" font-family="Inter,Arial,sans-serif" font-weight="700">AU</text><circle cx="32" cy="14" r="5" fill="#E8C547"/><path d="M29 14h6M32 11v6" stroke="#B8860B" stroke-width="1.2"/></svg>`,

  mantou: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><ellipse cx="32" cy="48" rx="22" ry="5" fill="#E8E0D0" opacity=".7"/><path d="M12 38c0-14 9-24 20-24s20 10 20 24c0 4-9 8-20 8s-20-4-20-8z" fill="#F5EDE0"/><path d="M18 34c2-8 7-14 14-14" fill="none" stroke="#FFFBF5" stroke-width="3" stroke-linecap="round" opacity=".8"/><path d="M24 22c3-2 7-3 12-2" fill="none" stroke="#D9CDB8" stroke-width="1.2" stroke-linecap="round"/></svg>`,

  beef: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><path d="M10 34c2-12 12-22 26-20 10 1 18 10 20 20 1 6-2 14-10 16-12 3-24-1-30-8-4-4-6-6-6-8z" fill="#A63D2F"/><ellipse cx="28" cy="34" rx="7" ry="5.5" fill="#F2C4B0"/><ellipse cx="40" cy="30" rx="4.5" ry="3.5" fill="#F2C4B0" opacity=".85"/></svg>`,


  aapl: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect width="64" height="64" rx="12" fill="#f2f2f2"/><path fill="#111" d="M41.2 18.2c-.9 1.1-2.4 1.9-3.8 1.8.1-1.2.6-2.5 1.5-3.4 1-1 2.5-1.7 3.8-1.8-.1 1.3-.6 2.5-1.5 3.4z"/><path fill="#111" d="M44.2 28.5c-1.4-.8-2.3-2.1-2.3-3.7 0-2.2 1.7-3.6 1.8-3.7-1.1-1.6-2.9-1.8-3.5-1.8-1.5-.2-2.9.9-3.7.9-.8 0-2-.9-3.3-.8-1.7 0-3.3 1-4.2 2.5-1.8 3.1-.5 7.7 1.3 10.2.9 1.2 1.9 2.6 3.3 2.5 1.3-.1 1.8-.8 3.4-.8s2 .8 3.4.8c1.4 0 2.3-1.2 3.2-2.4.9-1.4 1.3-2.8 1.3-2.9-.1 0-2.5-1-2.5-3.7 0-2.3 1.9-3.4 2-3.5z"/></svg>`,

  fridge: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="14" y="6" width="36" height="52" rx="4" fill="#E8ECF0" stroke="#B0B8C1" stroke-width="1.5"/><path d="M14 28h36" stroke="#B0B8C1" stroke-width="1.5"/><rect x="42" y="14" width="2.5" height="8" rx="1" fill="#8A939C"/><rect x="42" y="38" width="2.5" height="10" rx="1" fill="#8A939C"/></svg>`,

  washer: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="12" y="6" width="40" height="52" rx="4" fill="#E8ECF0" stroke="#B0B8C1" stroke-width="1.5"/><circle cx="20" cy="13" r="2.2" fill="#6B7280"/><circle cx="32" cy="38" r="14" fill="#CBD5E1" stroke="#94A3B8" stroke-width="1.5"/><circle cx="32" cy="38" r="10" fill="#BAE6FD"/></svg>`,

  ac: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="14" width="52" height="22" rx="4" fill="#F1F5F9" stroke="#94A3B8" stroke-width="1.5"/><rect x="10" y="18" width="44" height="10" rx="2" fill="#E2E8F0"/><path d="M18 40c0 4 2 8 6 10M32 40v12M46 40c0 4-2 8-6 10" fill="none" stroke="#93C5FD" stroke-width="2" stroke-linecap="round"/></svg>`,

  // maybach/ferrari use assets/*.png via item.img

  moutai: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="22" y="8" width="20" height="8" rx="2" fill="#8B1A1A"/><rect x="24" y="16" width="16" height="6" fill="#C4A35A"/><path d="M20 22h24l-2 34c0 2-2 4-10 4s-10-2-10-4l-2-34z" fill="#E8D5A3"/><rect x="24" y="28" width="16" height="18" rx="1" fill="#9B1B1B"/><text x="32" y="40" text-anchor="middle" fill="#F5E6B8" font-size="6" font-family="Noto Sans SC,sans-serif" font-weight="600">飞天</text><ellipse cx="32" cy="58" rx="10" ry="2.5" fill="#C4A35A"/></svg>`,

  iphone: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="16" y="6" width="32" height="52" rx="6" fill="#1c1c1e" stroke="#3a3a3c" stroke-width="1.5"/><rect x="19" y="10" width="26" height="42" rx="2" fill="#0a84ff"/><rect x="28" y="8" width="8" height="2" rx="1" fill="#3a3a3c"/><circle cx="32" cy="54.5" r="2" fill="#3a3a3c"/></svg>`,


  gas: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><rect x="12" y="10" width="28" height="44" rx="3" fill="#E8ECF0" stroke="#64748B" stroke-width="1.5"/><rect x="16" y="16" width="20" height="14" rx="2" fill="#1e293b"/><text x="26" y="26" text-anchor="middle" fill="#4ade80" font-size="8" font-family="JetBrains Mono,monospace" font-weight="600">92</text><rect x="18" y="34" width="8" height="4" rx="1" fill="#94a3b8"/><path d="M40 22h6c2 0 4 2 4 4v18c0 2 2 4 4 4" fill="none" stroke="#64748B" stroke-width="2.5" stroke-linecap="round"/><circle cx="54" cy="48" r="3" fill="#64748B"/></svg>`,

  macbook: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <rect x="8" y="14" width="48" height="32" rx="3" fill="#1d1d1f" stroke="#3a3a3c" stroke-width="1.2"/>
  <rect x="11" y="17" width="42" height="26" rx="1.5" fill="#4a90d9"/>
  <path d="M6 48h52c0 2-4 4-26 4S6 50 6 48z" fill="#c7c7cc"/>
  <rect x="28" y="49" width="8" height="1.5" rx="0.5" fill="#8e8e93"/>
</svg>`,

  beijing: `<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg"><path d="M8 48h48v4H8z" fill="#94a3b8"/><path d="M14 48V28l10-8 10 8v20" fill="#cbd5e1" stroke="#64748B" stroke-width="1.2"/><path d="M34 48V22l8-6 8 6v26" fill="#e2e8f0" stroke="#64748B" stroke-width="1.2"/><rect x="20" y="34" width="5" height="5" fill="#64748B"/><rect x="27" y="34" width="5" height="5" fill="#64748B"/><rect x="40" y="30" width="5" height="5" fill="#64748B"/><rect x="47" y="30" width="5" height="5" fill="#64748B"/><path d="M24 20l6-4 6 4" fill="none" stroke="#dc2626" stroke-width="1.5"/><rect x="28" y="42" width="6" height="6" fill="#475569"/></svg>`,
};

const ITEMS = [
  { id: "btc", name: "比特币", unit: "BTC", decimals: 6, art: "btc", getPrice: () => prices.BTC_CNY, liveKey: "btc", tag: "BTC" },
  { id: "gold", name: "黄金", unit: "克", decimals: 2, art: "gold", getPrice: () => prices.GOLD_CNY, liveKey: "gold", tag: "AU9999" },
  { id: "mantou", name: "馒头", unit: "个", decimals: 0, art: "mantou", getPrice: () => BASELINE.mantou, retail: true },
  { id: "beef", name: "牛肉", unit: "kg", decimals: 2, art: "beef", getPrice: () => BASELINE.beef, retail: true },
  { id: "moutai", name: "飞天茅台", unit: "瓶", decimals: 2, art: "moutai", getPrice: () => BASELINE.moutai, retail: true, tag: "500ml" },
  { id: "iphone", name: "iPhone", unit: "台", decimals: 2, art: "iphone", getPrice: () => BASELINE.iphone, retail: true, tag: "18 Pro Max" },
  { id: "macbook", name: "MacBook Air", unit: "台", decimals: 2, art: "macbook", getPrice: () => BASELINE.macbook, retail: true, tag: "13\" M5" },
  { id: "luckin", name: "瑞幸拿铁", unit: "杯", decimals: 0, art: "luckin", img: "assets/luckin.png", getPrice: () => BASELINE.luckin, retail: true },
  { id: "gas", name: "汽油92#", unit: "升", decimals: 1, art: "gas", getPrice: () => BASELINE.gas92, retail: true, tag: "北京" },
  { id: "beijing", name: "北京房价", unit: "㎡", decimals: 3, art: "beijing", getPrice: () => BASELINE.beijing_m2, retail: true, tag: "二手均价" },
  { id: "tsla", name: "特斯拉", unit: "股", decimals: 4, art: "tsla", img: "assets/tesla.png?v=whitebg", getPrice: () => prices.TSLA_CNY, liveKey: "tsla", tag: "TSLA" },
  { id: "aapl", name: "苹果", unit: "股", decimals: 4, art: "aapl", getPrice: () => prices.AAPL_CNY, liveKey: "aapl", tag: "AAPL" },
  { id: "fridge", name: "冰箱", unit: "台", decimals: 2, art: "fridge", getPrice: () => BASELINE.fridge, retail: true },
  { id: "washer", name: "洗衣机", unit: "台", decimals: 2, art: "washer", getPrice: () => BASELINE.washer, retail: true },
  { id: "ac", name: "空调", unit: "台", decimals: 2, art: "ac", getPrice: () => BASELINE.ac, retail: true },
  { id: "maybach", name: "迈巴赫", unit: "辆", decimals: 4, art: "maybach", img: "assets/maybach.png", getPrice: () => BASELINE.maybach, retail: true, tag: "S480" },
  { id: "ferrari", name: "法拉利", unit: "辆", decimals: 4, art: "ferrari", img: "assets/ferrari.png", getPrice: () => BASELINE.ferrari, retail: true, tag: "Roma" },
];

function parseAmount(raw) {
  if (raw == null) return NaN;
  let s = String(raw).trim().replace(/[,，\s]/g, "");
  if (!s) return NaN;
  const wan = s.match(/^([\d.]+)万$/);
  if (wan) return parseFloat(wan[1]) * 10000;
  if (!/^-?[\d.]+$/.test(s)) return NaN;
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : NaN;
}

function trimNum(n, maxDecimals) {
  const fixed = n.toFixed(maxDecimals);
  return fixed.replace(/\.?0+$/, "") || "0";
}

function formatQuantity(n, decimals) {
  if (!Number.isFinite(n)) return "—";
  if (n === 0) return "0";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 10000 && decimals <= 2) {
    const wan = abs / 10000;
    if (wan >= 10000) return sign + trimNum(wan / 10000, 2) + " 亿";
    const d = wan >= 100 ? 1 : 2;
    return sign + trimNum(wan, d) + " 万";
  }
  if (decimals > 2) {
    let s = abs.toFixed(decimals);
    s = s.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
    return sign + s;
  }
  return sign + trimNum(abs, decimals);
}

function formatCNYDisplay(n) {
  if (!Number.isFinite(n)) return "￥—";
  return "￥" + Math.round(n).toLocaleString("zh-CN");
}

function statusTag(item) {
  if (item.retail) return "参考零售价";
  if (item.liveKey) return prices.live[item.liveKey] ? "实时" : "参考价";
  return "";
}

function computeRows(amount) {
  const valid = Number.isFinite(amount) && amount >= 0;
  return ITEMS.map((item) => {
    const price = item.getPrice();
    const qty = valid && price > 0 ? amount / price : NaN;
    return {
      ...item,
      qty,
      qtyStr: valid ? formatQuantity(qty, item.decimals) : "—",
      price,
    };
  });
}

function renderCards(amount) {
  const rows = computeRows(amount);
  document.getElementById("cards").innerHTML = rows
    .map((row) => {
      const st = statusTag(row);
      const tagParts = [row.tag, st].filter(Boolean);
      const tag = tagParts.length
        ? `<span class="card-tag">${tagParts.join(" · ")}</span>`
        : "";
      return `
        <article class="card" data-id="${row.id}">
          <div class="card-art" aria-hidden="true">${row.img ? `<img src="${row.img}" alt="${row.name}" width="52" height="52" loading="lazy"/>` : (ART[row.art] || "")}</div>
          <div class="card-body">
            <div class="card-name-row">
              <span class="card-name">${row.name}</span>
              ${tag}
            </div>
            <div class="card-value">${row.qtyStr}<span class="card-unit">${row.unit}</span></div>
          </div>
        </article>`;
    })
    .join("");
}

function updateShareCard(amount) {
  document.getElementById("shareAmount").textContent = formatCNYDisplay(amount);
  document.getElementById("shareSlogan").textContent = SHARE_SLOGAN;
  document.getElementById("shareQrLabel").textContent = SHARE_QR_LABEL;

  const byId = Object.fromEntries(computeRows(amount).map((r) => [r.id, r]));
  const rows = SHARE_ITEM_IDS.map((id) => byId[id]).filter(Boolean);

  document.getElementById("shareGrid").innerHTML = rows
    .map(
      (row) => `
      <div class="share-item">
        <div class="share-item-art">${row.img ? `<img src="${row.img}" alt="" width="40" height="40"/>` : (ART[row.art] || "")}</div>
        <div>
          <div class="share-item-name">${row.name}${row.tag ? " · " + row.tag : ""}</div>
          <div class="share-item-val">${row.qtyStr} ${row.unit}</div>
        </div>
      </div>`
    )
    .join("");
}

async function ensureShareQr() {
  const el = document.getElementById("shareQr");
  if (!el || el.dataset.ready === SHARE_URL) return;
  const src = "/api/qr?data=" + encodeURIComponent(SHARE_URL);
  // Client-side QR lib as optional enhancement; server PNG is the reliable path
  const apply = (url) => {
    el.src = url;
    el.dataset.ready = SHARE_URL;
    return new Promise((resolve) => {
      if (el.complete) return resolve();
      el.onload = () => resolve();
      el.onerror = () => resolve();
    });
  };
  try {
    if (typeof QRCode !== "undefined") {
      const dataUrl = await QRCode.toDataURL(SHARE_URL, {
        width: 224,
        margin: 1,
        color: { dark: "#111111", light: "#ffffff" },
        errorCorrectionLevel: "M",
      });
      await apply(dataUrl);
      if (el.naturalWidth > 0) return;
    }
  } catch (_) {
    /* fall through */
  }
  await apply(src);
}

function updateStatusUI() {
  const el = document.getElementById("priceStatus");
  const text = document.getElementById("statusText");
  const hint = document.getElementById("resultsHint");
  const keys = ["btc", "gold", "tsla", "aapl"];
  const liveCount = keys.filter((k) => prices.live[k]).length;
  const line = "BTC / 黄金 / TSLA / AAPL 为实时行情；其余为参考零售价。";

  el.classList.remove("live", "partial");
  if (liveCount === keys.length) {
    el.classList.add("live");
    text.textContent = "实时行情";
  } else if (liveCount > 0) {
    el.classList.add("partial");
    text.textContent = "部分实时";
  } else {
    text.textContent = "参考价";
  }
  // Single slim footer line only
  hint.textContent = line;
}

async function fetchLivePrices(_force) {
  // Public cannot force upstream refresh (admin-only). Cache TTL handles freshness.
  const url = "/api/prices";
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (data.USD_CNY > 0) prices.USD_CNY = data.USD_CNY;
    if (data.BTC_CNY > 0) {
      prices.BTC_CNY = data.BTC_CNY;
      prices.live.btc = true;
    }
    if (data.GOLD_CNY > 0) {
      prices.GOLD_CNY = data.GOLD_CNY;
      prices.live.gold = true;
    }
    if (data.TSLA_CNY > 0) {
      prices.TSLA_CNY = data.TSLA_CNY;
      prices.live.tsla = true;
    } else if (data.TSLA_USD > 0 && prices.USD_CNY > 0) {
      prices.TSLA_CNY = data.TSLA_USD * prices.USD_CNY;
      prices.live.tsla = true;
    }
    if (data.AAPL_CNY > 0) {
      prices.AAPL_CNY = data.AAPL_CNY;
      prices.live.aapl = true;
    } else if (data.AAPL_USD > 0 && prices.USD_CNY > 0) {
      prices.AAPL_CNY = data.AAPL_USD * prices.USD_CNY;
      prices.live.aapl = true;
    }
    prices.sources = data.sources || {};
    prices.fetchedAt = data.fetched_at || null;
    return data;
  } catch (err) {
    console.warn("live prices failed", err);
    return null;
  }
}

function syncChips(amount) {
  const chips = document.querySelectorAll(".chip");
  let matched = false;
  chips.forEach((chip) => {
    const v = chip.dataset.amount;
    if (v === "custom") return;
    const on = Number.isFinite(amount) && amount === Number(v);
    chip.classList.toggle("active", on);
    if (on) matched = true;
  });
  const custom = document.getElementById("chipCustom");
  if (matched) custom.classList.remove("active");
  else if (Number.isFinite(amount)) {
    custom.classList.add("active");
    chips.forEach((c) => {
      if (c.dataset.amount !== "custom") c.classList.remove("active");
    });
  }
}

function currentAmount() {
  return parseAmount(document.getElementById("amount").value);
}

function refreshUI() {
  const amount = currentAmount();
  syncChips(amount);
  renderCards(amount);
  updateShareCard(amount);
  updateStatusUI();
}

function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    el.hidden = true;
  }, 2200);
}

function buildTextSummary(amount) {
  const rows = computeRows(amount);
  const lines = [
    `存款价值转换`,
    `金额：${formatCNYDisplay(amount)}`,
    SHARE_SLOGAN,
    "",
    ...rows.map((r) => `${r.name}${r.tag ? "(" + r.tag + ")" : ""}：${r.qtyStr} ${r.unit}`),
    "",
    SHARE_URL,
    "仅供参考，不构成建议。",
  ];
  return lines.join("\n");
}

async function copyResults() {
  const text = buildTextSummary(currentAmount());
  try {
    await navigator.clipboard.writeText(text);
    track("copy");
    showToast("已复制结果");
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    track("copy");
    showToast("已复制结果");
  }
}

async function saveImage() {
  const amount = currentAmount();
  if (!Number.isFinite(amount)) {
    showToast("请先输入有效金额");
    return;
  }
  updateShareCard(amount);
  await ensureShareQr();

  const card = document.getElementById("share-card");
  const btn = document.getElementById("btnSave");
  btn.disabled = true;
  btn.textContent = "生成中…";
  card.classList.add("capture");
  try {
    if (typeof html2canvas !== "function") throw new Error("html2canvas 未加载");
    // brief paint
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const canvas = await html2canvas(card.querySelector(".share-card-inner"), {
      backgroundColor: "#f7f6f3",
      scale: 2,
      useCORS: true,
      logging: false,
    });
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("无法生成图片");

    const fileName = `存款价值转换-${Math.round(amount)}.png`;
    const file = new File([blob], fileName, { type: "image/png" });

    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      try {
        await navigator.share({
          files: [file],
          title: "存款价值转换",
          text: SHARE_SLOGAN,
        });
        track("share"); // Web Share success only — not save_image
        showToast("已分享");
        return;
      } catch (err) {
        if (err && err.name === "AbortError") return; // user cancel: track nothing
        // fall through to download
      }
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
    track("save_image"); // download path only
    showToast("图片已保存");
  } catch (err) {
    console.error(err);
    showToast("保存失败，请重试");
  } finally {
    card.classList.remove("capture");
    btn.disabled = false;
    btn.textContent = "保存图片";
  }
}

function init() {
  const preview = isSharePreview();
  if (!preview && !document.hidden) {
    try {
      if (!sessionStorage.getItem("dvc_viewed")) {
        sessionStorage.setItem("dvc_viewed", "1");
        track("view");
      }
    } catch {
      track("view");
    }
  }
  if (preview) {
    document.querySelector("header")?.setAttribute("hidden", "");
    document.querySelector("main")?.setAttribute("hidden", "");
    document.querySelector("footer")?.setAttribute("hidden", "");
    document.body.style.background = "#e8e6e1";
  }
  const input = document.getElementById("amount");

  document.getElementById("chips").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    if (btn.dataset.amount === "custom") {
      input.focus();
      input.select();
      syncChips(currentAmount());
      return;
    }
    input.value = String(Number(btn.dataset.amount));
    refreshUI();
  });

  input.addEventListener("input", refreshUI);
  input.addEventListener("focus", () => input.select());
  document.getElementById("btnCopy").addEventListener("click", copyResults);
  document.getElementById("btnSave").addEventListener("click", saveImage);
  document.getElementById("btnRefresh").addEventListener("click", async () => {
    const t = document.getElementById("btnRefresh");
    t.disabled = true;
    t.textContent = "刷新中…";
    await fetchLivePrices(true);
    refreshUI();
    t.disabled = false;
    t.textContent = "刷新行情";
    const any = Object.values(prices.live).some(Boolean);
    showToast(any ? "行情已更新" : "仍使用参考价");
  });

  refreshUI();
  ensureShareQr().then(() => {
    if (new URLSearchParams(location.search).has("sharepreview")) {
      const card = document.getElementById("share-card");
      card.classList.add("capture");
      card.style.opacity = "1";
      card.style.position = "static";
      card.style.left = "auto";
      card.style.zIndex = "1";
      card.style.margin = "24px auto";
      document.body.style.background = "#ddd";
      document.querySelector("header")?.setAttribute("hidden", "");
      document.querySelector("main")?.setAttribute("hidden", "");
      document.querySelector("footer")?.setAttribute("hidden", "");
    }
  });
  fetchLivePrices(false).then(() => refreshUI());
}

document.addEventListener("DOMContentLoaded", init);
