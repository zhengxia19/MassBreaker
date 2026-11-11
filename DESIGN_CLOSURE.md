# Mass Breaker 项目状态与实施入口

**更新日期：** 2026-11-11。本文描述当前工作区，不代表已完成游戏开发。

## 1. 当前成果与完成边界

| 范围 | 当前成果 | 未完成事项 |
|---|---|---|
| 产品与工程设计 | 玩法、算法、数据格式、UI、视觉、任务依赖及验收标准 | C++ 实现与运行验证 |
| 关卡内容 | 30 份 Tiled 源、运行时 JSON、统计清单及预览 | Tiled GUI 操作确认、逐关人工通关与平衡 |
| 关卡工具 | 导出、校验、几何筛查、预览及 18 项回归测试 | 构建流水线集成 |
| 第三方依赖 | `third_party/SDL3/` 子模块已检出 `release-3.4.20`，提交 `f00dc919ca35b9756316e86c4777392de442f9b2` | 字体/音频依赖在 T12 接入并验证 |
| 游戏工程 | T01–T17 已定义交付与验收 | 尚无项目顶层 CMake、C++ 游戏源码、Windows 可执行程序或 Android APK/AAB |
| 运行质量 | 已定义功能、视觉与性能门槛 | 真机运行、字体与音频授权、30 关试玩、性能采样及发行 |

本地核验命令、结果和未验证范围见 [DESIGN_VALIDATION_REPORT.md](DESIGN_VALIDATION_REPORT.md)。

## 2. 实施入口

可以从 [T01 基础工程](docs/05_DEVELOPMENT_TASKS.md) 开始开发。T01/T02 固定实际工具链并形成双平台构建记录；T03–T09 完成关卡加载、单球和道具多球闭环；T10–T12 完成 UI、存档和正式资源；T13–T17 完成内容、兼容性与发行验收。

核心行为和公共接口以 [算法规范](docs/12_CORE_ALGORITHMS.md) 为准；玩法参数来自 [gameplay.json](assets/config/gameplay.json)，视觉参数来自 [visual.json](assets/config/visual.json)。实施时直接维护对应正文，并同步任务和验收用例。

手机性能与低功耗已作为实现约束：按状态阻塞等待、游戏目标 60 FPS、READY 空闲零 tick、后台停帧、预分配复用快照、有序活动表、增量 CPU 砖图、轴向碰撞快速路径及有界视觉预算。物理仍为 120 Hz，规则事件完整保留。T04–T07 直接实现，T08/T09 采集轻量记录，T12 检查正式效果，T16 完整验收；精确功耗按设备能力单列，收益尚未实测。

## 3. 资源检查入口

在项目根目录运行：

```powershell
python -B -m unittest discover -s tools/level-export -p "test_*.py" -v
python -B tools/level-export/validate.py --dir assets/levels --source levels-src
python -B tools/level-export/geometry.py --dir assets/levels
```

关卡修改遵循 [数据规范](docs/04_LEVEL_DATA_SPEC.md)：Tiled 源 → JSON → manifest/PNG → 完整检查。静态检查不能替代人工通关，C++ 测试规格不能计为已执行测试，设计 PNG 不能计为运行截图。
