# 站点运行手册（定时任务全景）

线上：https://lacyleotao-eng.github.io/global-hotspot-radar/
数据源：本仓库 `data/`；发布方式：`git push` → GitHub Pages 自动构建（**不要用 workbuddy_sites_deploy**，本账号该工具只会覆盖另一款应用）。

## 一、每日链路

| 时间 | 任务 | 产出 | 是否 push |
|---|---|---|---|
| 07:30 | 国内热点采集（公众号/头条/抖音/知乎/微博…） | `data/inbox/cn-*.json` → `data/items.json` | 否 |
| 12:30 | 海外热点采集（X/Reddit/HN/GitHub/PH…） | `data/inbox/global-*.json` → `data/items.json` | 否 |
| 18:00 | 爆款采集与对标 | `data/viral-inbox/` → `data/viral/benchmark.json` | 是 |
| 20:30 | 评分 · TOP3 全覆盖成品稿 · 自制信息卡 · 自检 · 发布 | `data/picks.json`、`data/ready/*.json`、`data/audit.json`、`assets/images/*.jpeg` | 是 |
| 23:30 | 发布后线上验收与失败兜底 | 只读复核；不通过则补稿或重推 | 视情况 |

每周一 10:00 —— 站点体检：归档瘦身、爆款库合规复查、采集通道健康、坏链抽检、周报。

## 二、互相兜底的规则

- 07:30 / 12:30 只入库不发布，所以**当天数据上线完全依赖 20:30 那一次 push**。
- 18:00 若失败，20:30 会拿旧的 `benchmark.json` 当写作指标（不会崩，但指标会偏旧），验收任务应在报告里点出。
- 23:30 是 20:30 的安全网：本地没稿 → 补写；有稿没上线 → 重推；构建失败 → 修或报错。**最多 2 轮，不许伪造通过。**
- 所有情报站任务统一跑最低倍率模型（当前 `hy4flash-free` x0.00）；429 由「模型额度哨兵」每 4 小时自动升降档，上限 x0.15。

## 三、硬闸门（写死在脚本里，不靠自觉）

- `scripts/ingest_viral.py`：平台与域名不一致直接拒收，拒因写 `data/viral/meta.json` 的 `rejected`。
- `scripts/audit_ready.py --strict`：任一成品稿 <85 分，或 TOP3 选题有缺稿，退出码 1。
- `scripts/archive_ready.py --dry-run`：归档前先看会动哪些文件，当天/昨天的稿不允许出现在列表里。

## 四、体积与归档

每天新增 1 套成品稿（4 形态 JSON）+ 8 张 1080×1440 信息卡，年化约 300MB。每周体检时：

- `python3 scripts/archive_ready.py`：早于 45 天的 JSON 移入 `data/archive/ready/`（摘要累积到 `data/archive/ready-index.json`）；早于 21 天、超 260KB 的图压到 1200px / q78（同名覆盖，历史引用不断）。
- 归档后必须 `python3 scripts/make_ready_embed.py` 重建索引，再跑一次 `--strict` 确认没把当天稿子弄丢。
- **归档只移动、压缩只覆盖，永不 `rm` 成品稿或图片。**

## 五、已踩过的坑（别再踩）

- `*-embed.js` 被 GitHub Pages 缓存约 10 分钟：线上核对一律 `curl` 带随机参数，`WebFetch` 有 15 分钟缓存不能用。
- 自制信息卡渲染走本机 Chrome 无头（`scripts/make_cards.py`），不消耗豆包额度；豆包只补场景图，额度为 0 就直接放弃。
- 公众号贴图没有搜索引擎入口，只能从微信客户端「···→复制链接」取 `mp.weixin.qq.com/s/xxx`，用 `fetch_wechat_url.py` 解析（`type=9` + `item_show_type=8` 即贴图）。
- `git add -A` 会带上 `.workbuddy`，提交前 `git reset .workbuddy`。
