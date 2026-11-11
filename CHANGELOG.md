# 文档修订记录

## V1.3.1 — 2026-11-11（固定步终态 / 公共接口 / 验收依赖 / 砖层尺寸修订）

- **主循环 P0**：每个 fixedTick 后重查阶段与代际，进入 WON、LOST 或失球转入 READY（以及 READY→PLAYING）即停止当前追赶、清空累积器；保留该 tick 的事件，补 LOOP-01..04 测试规格。
- **接口 P0**：HUD 唯一路径为 `FramePacket.currentTick.hud`；正式事件枚举含 `PaddleHit`，统一 `ItemCollected`，删除实现需要另造同义事件的空间。控制通道 0 tick `SessionReset` 必须同帧交付，补 FRAME-06/API-01..02。
- **任务依赖 P1**：T10 仅页面交互阶段验收（允许测试注入 SaveResult 与临时字体）；T11 真正存档/下一关保存成功门槛；T12 明确依赖 T11 并负责正式字体/音效/视觉的全 UI 集成验收。T01–T17 编号保持。
- **关卡导出 P0**：实际修复 `bricks.width/height` 未校验缺陷。除检查地图外严格要求砖层自身宽高整数 96×160；48×320、160×96、96×159（数据长度不变）均拒绝。`test_export.py` 9→12 个测试，验证失败不覆盖已有 JSON。
- 同步更新架构、算法、关卡数据、UI、视觉、任务、测试、总方案、README、核验报告；30 关地图数据及视觉设计稿未改；仍无 C++ 实现与 Android 真机证据。


## V1.3 — 2026-11-11（视觉与运行契约收口）

- `10_UI_UX_DESIGN.md` / `12_CORE_ALGORITHMS.md`：分离物理 GameplayCommand 与不依赖 fixed tick 的 ControlCommand。`PAUSED` 阶段立即处理 Resume/Retry/退出及模态确认；系统返回和手指捕获规则一致。
- 统一输入层级为：系统挂起/焦点 > 模态 > 暂停面板/导航 > HUD 暂停按钮 > 世界控制；禁止确认窗点击穿透。
- `03_TECHNICAL_ARCHITECTURE.md` / `12_CORE_ALGORITHMS.md`：为挡板、道具、球补齐绘制数据，`FrameCollector` 每 tick 复制所有重要事件并在显示帧一次消费，严格使用相邻物理 tick 的快照插值；一显示帧最多一次完整砖纹理上传。
- 新增 `assets/config/visual.json`、`docs/14_VISUAL_DESIGN_AND_FEEDBACK.md`、`design/ui/final/` 8 页细化稿、L028 多球画面，以及真实 L003 微砖画面。绘图工具 `tools/visual-preview/render_ui.py` 可复现，不打包字体。
- `tools/level-export/export.py` 明确拒绝非零 `offsetx/offsety/x/y`、非默认 parallax、group 图层；`test_export.py` 新增 9 项回归，包含两层偏移 `8` 必须报错及 30 关一致性。
- `05_DEVELOPMENT_TASKS.md`、`07_TEST_AND_ACCEPTANCE.md` 增加 CTRL/FRAME/视觉/offset 的明确验收，不增加大型预研阶段。
- 30 份 Tiled/JSON 关卡数据及原有布局**未改变**；它们仍需真实 C++ 游戏和人工试玩验证。

## V1.2 — 2026-11-10（设计闭环版）

- 完成上一轮 D01–D06 六项必需整改，形成 [`DESIGN_CLOSURE.md`](DESIGN_CLOSURE.md)。
- 新增 [`12_CORE_ALGORITHMS.md`](docs/12_CORE_ALGORITHMS.md)：CCD、并列接触、球池、事件处理、渲染合约、错误行为及 14 类关键测试。
- 新增 [`13_LEVEL_BALANCE.md`](docs/13_LEVEL_BALANCE.md)：实际更新 30 关目标砖及 B 数量；不再把 4,000+ 砖的单球开局或 L028 仅 5 个 B 当作已完成平衡设计。
- 新增 [`assets/config/gameplay.json`](assets/config/gameplay.json) 作为数值唯一权威。
- 实际重写 30 份 Tiled `.tmj`，同步导出 30 份游戏 `.json`、布局 PNG、关卡总览和统计 manifest。
- 更新 `export.py/validate.py` 的显式校验及源对照，增加固定墙结构几何 `geometry.py`、`build_manifest.py` 和 `render.py`。
- 将原 `T01–T19` 更新为带依赖的 `T01–T17`，修复关卡加载和 +3 验收顺序。
- 同步 PRD、技术架构、关卡规范、UI 事件合约、总方案、测试、README。

**仍需真实开发：** C++ 游戏引擎、Windows/Android 构建、30关试玩与真实机型性能；静态校验不能代替这些证据。

## V1.1 — 2026-11-10

- 补充 8 种页面 UI/UX 线框图及 30 关初版 Tiled/JSON/预览。
- 初步提供 Tiled 导出与基础格式校验；关卡数值和碰撞边界尚不完整。
