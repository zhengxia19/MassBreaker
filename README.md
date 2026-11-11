# Mass Breaker — Android 微型打砖块游戏

**当前文档基线：** 2026-11-11；产品范围为 V1。

**交付类型：** 正式项目设计、30 关可编辑资源与导出/校验工具；**不是已编译游戏、APK 或真实试玩报告**。

## 已决定的项目基线

- **C++20 + SDL3 3.4.20 + Android GLES 3.0 / Windows GL 3.3 Core**；CMake + Gradle/NDK。
- 规则网格 96×160、世界 24×40；大量微型砖无独立物理节点；小球池单线程 CCD、容量上限 1024。
- 初始 1 球；**仅通过接到 B 砖掉落的 +3 道具新增球**；无播放加速、无球球碰撞、无联网。
- 6 章 30 关、8 个页面，Tiled 源、运行时 JSON、预览图，首关从 320 个目标砖开始，后期最高 5,200 个。

## 仓库与本机开发环境

- **远程仓库：** `git@github.com:zhengxia19/MassBreaker.git`（GitHub，MIT 许可）。主分支为 `master`（见[工程规范](docs/08_ENGINEERING_RULES.md) §3），远端 `main` 与其保持同步。
- **第三方子模块：** `third_party/SDL3` → <https://github.com/libsdl-org/SDL>，tag `release-3.4.20`（commit `f00dc919ca35b9756316e86c4777392de442f9b2`）。
- **本机开发环境（记录于 2026-11-11）：**

| 组件 | 本机实际版本 / 路径 |
|---|---|
| 编译器 | VS 2026 Build Tools 18.8.2，MSVC 工具集 14.51.36231，实测 `cl /std:c++20` 编译通过 |
| Windows SDK | 10.0.26100 |
| CMake / Ninja | VS 自带 4.3.1 / 1.13.2（`Common7\IDE\CommonExtensions\Microsoft\CMake\`）；Android 构建另可用 SDK 内置 CMake 3.22.1 |
| Git | 2.49.0 |
| Python | 3.14.6（`C:\Python314`），已装 Pillow 12.3 / numpy / shapely / lxml |
| Android SDK | `D:\DevEnv\android-sdk`：platforms android-36 / 37.0 / 37.2、build-tools 36.0.0、NDK 28.2.13676358（r28c）、platform-tools（adb）、emulator |
| JDK | `D:\DevEnv\tools\jdk-21`（OpenJDK 21.0.12 LTS） |
| 尚未安装 | SDL3_ttf 3.2.2 / SDL3_mixer 3.2.4（按任务在 T12 接入）、Tiled 1.12.2（仅编辑关卡时需要） |

> [构建规范](docs/06_BUILD_AND_RELEASE.md) §1 的"Visual Studio 2022"基线在本机以 VS 2026 Build Tools 落实：MSVC 工具集 14.51 完整支持 C++20，视为兼容基线。T01 首次实编译后按 06 §3 把实际构建命令与产物路径回写本节。

## 从哪里开始读

| 文件 | 作用 |
|---|---|
| [DESIGN_CLOSURE.md](DESIGN_CLOSURE.md) | 当前成果、实施入口与未完成边界 |
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
| [docs/12_CORE_ALGORITHMS.md](docs/12_CORE_ALGORITHMS.md) | **连续碰撞、多球、增球、事件顺序、输入/渲染接口** |
| [docs/13_LEVEL_BALANCE.md](docs/13_LEVEL_BALANCE.md) | 30 关数值与 B 砖分布 |
| [docs/14_VISUAL_DESIGN_AND_FEEDBACK.md](docs/14_VISUAL_DESIGN_AND_FEEDBACK.md) | **微格、球、板、掉落物、UI 视觉与动效详细实现规范** |
| [assets/config/visual.json](assets/config/visual.json) | **UI 色板、主题及效果参数的唯一来源** |
| [design/ui/final/all_8_final_screens.png](design/ui/final/all_8_final_screens.png) | 8 屏设计稿（设计示意） |
| [design/ui/final/03_gameplay_multiball.png](design/ui/final/03_gameplay_multiball.png) | 从 L028 JSON 绘制的多球画面设计稿 |
| [assets/config/gameplay.json](assets/config/gameplay.json) | **游戏数值唯一配置权威** |
| [design/levels/all_30_levels.png](design/levels/all_30_levels.png) | 30 关当前资源直出预览 |
| [design/levels/manifest.json](design/levels/manifest.json) | 30 关目标数/墙/B/耐久统计 |
| [levels-src/](levels-src/) | 30 份 `.tmj` 关卡编辑源 |
| [assets/levels/](assets/levels/) | 对应运行时 JSON |

## 资源生成与校验

在项目根目录运行：

```bash
python -B tools/level-export/validate.py --dir assets/levels --source levels-src
python -B tools/level-export/geometry.py --dir assets/levels
python -B -m unittest discover -s tools/level-export -p "test_*.py" -v
```

修改某关的正确顺序：改 Tiled `.tmj` → `export.py` 导出 JSON → `build_manifest.py` 更新清单 → `render.py` 更新预览 → 完整校验。预览图工具只在设计机需要 Pillow，Android 游戏不依赖 Python。

如需在 Windows 上重绘 UI 参考 PNG：安装 Pillow，并设置 `MB_UI_FONT` 为本机有授权的中文字体路径；执行 `python -B tools/visual-preview/render_ui.py`。工具不附带字体文件。

手机性能与低功耗已作为实现约束：按状态阻塞等待、游戏目标 60 FPS、READY 空闲零 tick、后台停帧、预分配复用快照、有序活动表、增量 CPU 砖图、轴向碰撞快速路径及有界视觉预算。物理仍为 120 Hz，规则事件完整保留。T04–T07 直接实现，T08/T09 采集轻量记录，T12 检查正式效果，T16 完整验收；精确功耗按设备能力单列，收益尚未实测。

## 项目当前状态与下一步

**已完成：** 产品与工程设计，30 份 Tiled/JSON、统计和预览，关卡工具及其回归测试。SDL3 子模块已检出 `release-3.4.20`。

**待实施：** C++ 游戏工程、Windows/Android 构建、真实 UI 与存档、正式字体和音频、运行时 Shader、逐关人工试玩、真机性能及 APK/AAB。

**开发入口：** 运行上述资源检查后，按 [T01–T17](docs/05_DEVELOPMENT_TASKS.md) 开始实施。T01/T02 记录实际工具链和构建命令；T10 依赖 T08/T09 并使用真实游戏事件；T11/T12 完成持久化和正式 UI 联验；T16 按 [性能验收规范](docs/07_TEST_AND_ACCEPTANCE.md) 采样判定。设计资料已足以启动开发，运行效果仍须逐项验证。
