# 自驾行程规划 Skill

这是一个给 Codex / Agent 使用的自驾行程规划 skill。你可以输入类似 `D1/D2` 的中文行程文本，它会生成可核验的行程数据、手机友好的网页、交互式路线地图，并可选生成费用预算和 PDF。

主要能力：

- 解析中文行程：支持 `D1`、`D2`、`合肥 到 岳阳`、`重庆 回 合肥` 这类写法
- 生成标准数据：`trip-data.json`、`manifest.json`
- 生成中文网页：默认输出 `trip.html`，GitHub Pages 输出 `docs/index.html`
- 生成路线地图：HTML 内置交互式 Leaflet 地图，可选输出 `route-map.png`
- 支持高德真实路线：距离、时长、过路费、路线点位来自高德 Web 服务
- 支持无 key 预览：没有地图 key 时会用估算模式，并在 `manifest.json` 里明确标记
- 支持费用预算：电车补能、住宿、餐饮、景点门票、摆渡车、保险等
- 支持 PDF 导出：安装 Playwright 后可生成 PDF
- 适合 Agent 集成：每次运行都会写入 `manifest.json`，方便下游检查文件、警告和数据来源

## 在线 Demo

[打开 GitHub Pages Demo](https://twoer.github.io/self-drive-trip-planner/)

这个公开 demo 使用 `examples/simple-trip.txt` 生成，路线数据来自高德 / Amap API。仓库只提交生成后的静态 HTML、JSON 和图片，不保存任何 API key。

## 30 秒快速开始

```bash
git clone https://github.com/twoer/self-drive-trip-planner.git
cd self-drive-trip-planner
make install
make setup
make demo
open trip-output/trip.html
```

说明：

- `make install` 会创建本地 `.venv/` 并安装依赖，不污染系统 Python。
- `make setup` 会引导你创建本地 `.env`。
- `make demo` 会优先使用 `.env`、`AMAP_KEY` 或 `GAODE_KEY` 里的高德 key。
- 如果没有 key，会生成估算版预览，并在 `trip-output/manifest.json` 里写明 warning。

## 本地可视化编辑器

如果你不想直接写文本文件，可以启动本地编辑器：

```bash
make editor
```

然后打开：

```text
http://127.0.0.1:8765
```

编辑器支持粘贴自然语言行程、解析成 D1/D2 卡片、增删每天、编辑路线段和停留备注，并调用同一套生成引擎输出到 `trip-output/editor`。

编辑器前端使用 Vue 3 + TypeScript + Tailwind 构建，插件包会携带已经构建好的 `editor/dist`，普通用户运行 `make editor` 不需要安装 Node。开发编辑器时可以运行：

```bash
make editor-dev
```

重新构建前端：

```bash
make editor-build
```

编辑器默认使用 `estimate` 模式，方便没有高德 key 的用户先预览。配置 `AMAP_KEY` 或 `GAODE_KEY` 后，可以切换到 `auto` 或 `accurate`。

## 配置高德 Key

国内自驾路线建议使用高德 Web 服务 key。你可以在 [高德开放平台控制台](https://console.amap.com/dev/key/app) 创建 Web 服务 Key，然后写入本地 `.env`：

```bash
AMAP_KEY=你的高德Web服务Key
```

也支持：

```bash
GAODE_KEY=你的高德Web服务Key
```

本地 `.env` 已被 git 忽略，也不会被打进插件包。

## 安装成 Codex Skill

安装到默认 Codex skills 目录：

```bash
make install-skill
```

之后可以在 Codex 中让它使用 `$self-drive-trip-planner` 处理行程。

## 安装成 Codex 插件

下载最新插件包：

[self-drive-trip-planner-plugin.zip](https://github.com/twoer/self-drive-trip-planner/releases/download/v0.5.0/self-drive-trip-planner-plugin.zip)

完整安装说明见 [INSTALL.md](INSTALL.md)。

如果你想把当前仓库安装到自己的本地 Codex 插件市场：

```bash
make install-plugin
```

这个命令会：

- 构建干净的插件包
- 复制到 `~/plugins/self-drive-trip-planner`
- 更新 `~/.agents/plugins/marketplace.json`
- 执行 `codex plugin add self-drive-trip-planner@personal`

安装后请新开一个 Codex task，让 skill 列表刷新。

构建可分发的插件包：

```bash
make package-plugin
```

输出文件：

- `dist/self-drive-trip-planner/`
- `dist/self-drive-trip-planner-plugin.zip`

插件包会排除生成产物、本地缓存、`.env` 和 `.git` 等仓库元数据，只保留运行 skill 需要的文件。

校验插件包：

```bash
make check-plugin-package
```

如果本地有 Codex plugin validator，也可以运行：

```bash
make validate-plugin
```

## CLI 用法

先安装依赖：

```bash
make install
```

生成估算版预览：

```bash
python3 scripts/route_trip.py examples/simple-trip.txt --out ./trip-output --title "Demo 自驾游" --mode estimate
```

要求必须使用高德真实路线数据：

```bash
export AMAP_KEY="你的高德Web服务Key"
python3 scripts/route_trip.py examples/simple-trip.txt --out ./trip-output --title "Demo 自驾游" --mode accurate
```

## 可直接复制的完整输入示例

你可以把下面整段复制给 Agent 或保存成文本文件，然后替换成自己的路线、人数和费用：

```text
我们是两大一小（低于 1.2m），

开电车，电价 1.5 元/度，百公里综合电耗 18 度；
酒店每晚 300 元，
餐费每天 200 元；
景区：韶山景区、黄果树瀑布、小七孔，天眼景区（门票不要钱，摆渡车 50 元一人，保险 10 元一人），凤凰古城免费。
已确认景区价格：黄果树瀑布成人票 160 元，观光车 50 元一人，保险 10 元一人；小七孔成人票 120 元，观光车 40 元一人。

D1
合肥 到 岳阳
D2
岳阳 到 韶山
D3
韶山 到 凤凰古城
D4
凤凰古城 到 荔波
D5
荔波 到 小七孔
小七孔 到 中国天眼
中国天眼 到 安顺

D6
安顺 到 黄果树
黄果树 到 贵阳
D7
贵阳市区
D8
贵阳 到 茅台镇红军桥
茅台镇红军桥 到 遵义会议遗址
遵义会议遗址 到 重庆
D9
重庆市区
D10
重庆 回 合肥
```

替换建议：

- 把 `两大一小` 改成真实出行人数
- 把 `低于 1.2m` 或 `高于 1.2m` 改成儿童实际情况
- 把电价、百公里电耗、酒店、餐费改成你的预算
- 把景区名称和已确认价格改成你的行程
- 把 `D1`、`D2` 路线换成自己的每日路线

注意：CLI 默认不会自动联网查门票价格，它只解析你输入文本里的价格。如果你用 Codex / Agent，可以先只写景区名，让 Agent 查询官方或权威来源，再把查到的价格补到 `已确认景区价格：` 后面再运行生成。

## 费用预算写法

费用可以放在行程开头，也可以追加 `费用预算：` 段落：

```text
费用预算：
我们是两大一小（低于 1.2m），开电车，电价 1.5 元/度，百公里电耗 16 度；
酒店每晚 300 元，餐费每天 100 元；
小七孔成人票 120 元，中国天眼成人票 140 元。
```

也支持景区组件费用：

```text
景点门票：天眼景区门票不要钱，摆渡车 50 元一人，保险 10 元一人。
```

费用规则：

- 酒店晚数默认等于 `行程天数 - 1`
- 餐费天数默认等于 `行程天数`
- 成人票按全价计算
- 低于 1.2m 儿童默认免票
- 高于或等于 1.2m 儿童默认半价
- `摆渡车 50 元一人`、`保险 10 元一人` 会按总人数计算
- 识别到 `小七孔`、`黄果树`、`韶山`、`中国天眼` 等景区但没有配置价格时，会在费用页显示 `待补景点费用`
- 待补景点费用只做提醒，不会计入总费用
- 如果完全没有费用输入，费用 tab 会显示“费用计算未启用”的激活提醒

等价 CLI 参数示例：

```bash
python3 scripts/route_trip.py examples/simple-trip.txt \
  --out ./trip-output \
  --title "Demo 自驾游" \
  --mode estimate \
  --vehicle-type ev \
  --ev-kwh-price 1.5 \
  --hotel-nightly 300 \
  --meal-daily 100 \
  --adults 2 \
  --children-under-1-2m 1 \
  --attraction 小七孔=120 \
  --attraction 中国天眼=140
```

## 导出 PDF

PDF 依赖 Playwright。安装后运行：

```bash
make install-pdf
make demo-pdf
```

如果 Playwright 没安装，PDF 会跳过生成，原因会写入 `manifest.json`。

## SaaS 化方向

当前仓库已经把三层边界拆开：

- 路线和费用引擎：`scripts/route_trip.py`
- 本地 API：`scripts/editor_server.py`
- 可视化编辑器：`editor/`

如果后续做 SaaS 版本，建议保留前端编辑体验，把 Python 引擎抽成后端服务接口，再补用户账号、行程草稿、分享页、公开/私密权限、异步高德路线刷新和价格来源缓存。本地 skill 仍然适合 Agent 自动生成，SaaS 版本适合普通用户自己创建、分享和查看。

## 运行模式

- `auto`：默认模式；有 key 用高德 API，没有 key 用估算
- `estimate`：跳过 API，生成估算版，并明确标记数据来源
- `accurate`：要求每段驾车路线都必须来自高德 API，否则失败退出
- `publish-demo`：用于 GitHub Pages，会把结果写到 `docs/`
- `data-only`：只输出 `trip-data.json` 和 `manifest.json`，不生成网页和地图

兼容旧参数：`--no-api` 仍可使用，等价于 `--mode estimate`。

每次运行都会写 `manifest.json`。Agent 集成时应该优先读取它。

## 输入格式

基础格式：

```text
D1
合肥 到 岳阳
D2
岳阳 到 韶山
D3
韶山 到 凤凰古城
D4
凤凰古城 到 荔波
D5
荔波 到 小七孔
小七孔 到 中国天眼
中国天眼 到 安顺
D6
安顺 到 黄果树
黄果树 到 贵阳
D7
贵阳市区
D8
贵阳 到 茅台镇红军桥
茅台镇红军桥 到 遵义会议遗址
遵义会议遗址 到 重庆
D9
重庆市区
D10
重庆 回 合肥
```

支持的路线连接词：

- `到`
- `回`
- `返回`
- `->`
- `→`

没有路线连接词的行，例如 `贵阳市区`，会被当作当天停留备注。它会出现在 JSON 和 HTML 里，但不会计入驾车里程、时长、过路费和路线地图。

## 地图图片

`trip.html` 默认包含交互式 Leaflet 地图，可以缩放、拖动、点击路段查看详情。浏览器需要能访问地图瓦片资源。

如果还想额外生成可分享的 `route-map.png`，安装 Playwright：

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

没有 Playwright 时，PNG 会跳过生成，交互式 HTML 地图不受影响。

## API Key 和安全说明

不要提交 API key。请使用环境变量或本地 `.env`：

- `AMAP_KEY`
- `GAODE_KEY`

没有 key 时，脚本会尽量根据坐标估算，并在输出里标记：

- `source: "estimated"`
- `estimated: true`

使用 API 模式时，路线距离、时长、过路费和路线折线来自配置的地图服务。出发、预订或导航前，请以地图服务、景区、酒店和现场信息为准。

## Agent 集成约定

这个仓库适合被另一个 Agent 调用。推荐流程：

1. 把用户行程文本传给 `scripts/route_trip.py`
2. 明确选择 `--mode`
3. 读取 `manifest.json`
4. 检查 `manifest.files` 里的文件是否存在
5. 向用户报告 `manifest.data_source`、`manifest.totals` 和 `manifest.warnings`

GitHub Pages demo 使用：

```bash
make pages-demo
```

它会生成：

- `docs/index.html`
- `docs/trip-data.json`
- `docs/manifest.json`
- `docs/route-map.png`
- `docs/.nojekyll`

## 开发命令

运行测试：

```bash
make test
```

生成本地估算 demo：

```bash
make demo-estimate
```

有 `AMAP_KEY` 或 `GAODE_KEY` 时，生成高德 API demo：

```bash
make demo-api
```

生成 GitHub Pages demo：

```bash
make pages-demo
```

生成 20 条高密度随机 demo，用于 UI 压测：

```bash
make demo-batch
```

生成产物默认被 git 忽略，`docs/` 除外。`docs/` 用于 GitHub Pages，需要提交。
