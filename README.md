# Mass Breaker — Android 微型打砖块游戏

**设计交付版本：V1.3.1（主循环 / API / UI 验收 / Tiled 图层尺寸一致性修订版）**，2026-11-11  
**交付类型：** 正式项目设计、30 关可编辑资源与导出/校验工具；**不是已编译游戏、APK 或真实试玩报告**。

## 已决定的项目基线

- **C++20 + SDL3 3.4.20 + Android GLES 3.0 / Windows GL 3.3 Core**；CMake + Gradle/NDK。
- 规则网格 96×160、世界 24×40；大量微型砖无独立物理节点；小球池单线程 CCD、容量上限 1024。
- 初始 1 球；**仅通过接到 B 砖掉落的 +3 道具新增球**；无播放加速、无球球碰撞、无联网。
- 6 章 30 关、8 个页面，Tiled 源、运行时 JSON、预览图，首关从 320 个目标砖开始，后期最高 5,200 个。
- V1.2 已补齐碰撞与数值基线；V1.3 修订暂停控制、帧交接、输入优先级和非零图层偏移。**V1.3.1 追加每 tick 终态检查、统一 `frame.currentTick.hud` 与 11 种事件、拆分 T10/T11/T12 验收，并修复砖层自身宽高被忽略的导出错误。**

## 从哪里开始读

| 文件 | 作用 |
|---|---|
| [DESIGN_CLOSURE.md](DESIGN_CLOSURE.md) | **V1.3.1 修订范围、完成状态及开发边界** |
| [DESIGN_VALIDATION_REPORT.md](DESIGN_VALIDATION_REPORT.md) | 真实静态核验结果及其证据边界 |
| [PROJECT_PLAN.md](PROJECT_PLAN.md) | 项目总体方案与里程碑 |
| [docs/01_PRODUCT_REQUIREMENTS.md](docs/01_PRODUCT_REQUIREMENTS.md) | PRD 与功能范围 |
| [docs/02_GAMEPLAY_AND_LEVELS.md](docs/02_GAMEPLAY_AND_LEVELS.md) | 冻结的玩法、计分、多球规则 |
| [docs/03_TECHNICAL_ARCHITECTURE.md](docs/03_TECHNICAL_ARCHITECTURE.md) | C++ 模块划分、数据流与 GPU 接口 |
| [docs/04_LEVEL_DATA_SPEC.md](docs/04_LEVEL_DATA_SPEC.md) | Tiled/JSON schema、校验及资源流程 |
| [docs/05_DEVELOPMENT_TASKS.md](docs/05_DEVELOPMENT_TASKS.md) | **T01–T17 正式开发任务及依赖** |
| [docs/06_BUILD_AND_RELEASE.md](docs/06_BUILD_AND_RELEASE.md) | Windows / Android 构建计划、签名、发布 |
| [docs/07_TEST_AND_ACCEPTANCE.md](docs/07_TEST_AND_ACCEPTANCE.md) | 核心单测、30关试玩、Android 质量门槛 |
| [docs/08_ENGINEERING_RULES.md](docs/08_ENGINEERING_RULES.md) | Git、资源授权和工程规范 |
| [docs/09_REFERENCE_SOURCES.md](docs/09_REFERENCE_SOURCES.md) | 来源链接与参考素材 |
| [docs/10_UI_UX_DESIGN.md](docs/10_UI_UX_DESIGN.md) | **8 屏 UI 与交互规范、线框图** |
| [docs/11_LEVEL_DESIGN.md](docs/11_LEVEL_DESIGN.md) | **30 关逐关布局、资源链接和主要风险** |
| [docs/12_CORE_ALGORITHMS.md](docs/12_CORE_ALGORITHMS.md) | **新增：连续碰撞、多球、增球、事件顺序、输入/渲染接口** |
| [docs/13_LEVEL_BALANCE.md](docs/13_LEVEL_BALANCE.md) | 30 关数值与 B 砖分布（V1.2 数据不变） |
| [docs/14_VISUAL_DESIGN_AND_FEEDBACK.md](docs/14_VISUAL_DESIGN_AND_FEEDBACK.md) | **新增：微格、球、板、掉落物、UI 视觉与动效详细实现规范** |
| [assets/config/visual.json](assets/config/visual.json) | **新增：UI 色板、主题及效果参数的唯一来源** |
| [design/ui/final/all_8_final_screens.png](design/ui/final/all_8_final_screens.png) | 新 8 屏细化稿（设计示意） |
| [design/ui/final/03_gameplay_multiball.png](design/ui/final/03_gameplay_multiball.png) | 从 L028 JSON 绘制的多球画面设计稿 |
| [assets/config/gameplay.json](assets/config/gameplay.json) | **游戏数值唯一配置权威** |
| [design/ui/all_8_screens.png](design/ui/all_8_screens.png) | 8 屏线框图总览（概念图） |
| [design/levels/all_30_levels.png](design/levels/all_30_levels.png) | 30 关**本版本**资源直出预览 |
| [design/levels/manifest.json](design/levels/manifest.json) | 30 关目标数/墙/B/耐久统计 |
| [levels-src/](levels-src/) | 30 份 `.tmj` 关卡编辑源 |
| [assets/levels/](assets/levels/) | 对应运行时 JSON |

## 资源生成与校验（本包已经包含工具）

在项目包根目录运行：

```bash
python tools/level-export/validate.py --dir assets/levels --source levels-src
python tools/level-export/geometry.py --dir assets/levels
python -m unittest discover -s tools/level-export -p "test_*.py" -v
```

修改某关的正确顺序：改 Tiled `.tmj` → `export.py` 导出 JSON → `build_manifest.py` 更新清单 → `render.py` 更新预览 → 完整校验。预览图工具只在设计机需要 Pillow，Android 游戏不依赖 Python。

如需在 Windows 上重绘新的 UI 参考 PNG：安装 Pillow，并设置 `MB_UI_FONT` 为本机有授权的中文字体路径；执行 `python tools/visual-preview/render_ui.py`。工具不附带字体文件。

## 项目当前状态与下一步

**已完成：** 技术选型、界面/玩法/算法/数据/任务的设计契约；30 份对应 Tiled/JSON、预览图及工具脚本；V1.3.1 主循环与公共事件契约、分阶段 UI 验收，以及 offset 和砖层宽高导出器修复与实际 Python 回归测试。  
**未完成：** C++ 代码、Windows/Android 构建、人工试玩通过、真实设备性能结果、正式字体与音频、实际运行时 Shader、APK/AAB。设计稿不是游戏运行截图。

**开发入口**：首先使用本版 `tools/level-export/export.py` 更新仓库旧版脚本并执行 12 项测试，之后按 [`T01`](docs/05_DEVELOPMENT_TASKS.md) 开始 C++20 + SDL3 开发；不再另设技术选型或大型预研。
