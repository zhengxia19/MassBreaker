# 技术架构与工程接口（V1.3.1）

**编号：** MB-ARCH-003｜**决定：** C++20 + SDL3 3.4.20 + OpenGL ES 3.0（Android）/ OpenGL 3.3 Core（Windows）

## 1. 架构总览

```text
SDL3 Platform (window, touch, lifecycle, file/audio)
  └─ AppController (UI navigation, asset loading, fixed clock)
      ├─ GameSession (lives, score, game states, pickups, events)
      │   ├─ Simulation (BallPool, PaddleState, CCD solver)
      │   │    └─ BrickField (grid, HP, target count)
      │   └─ LevelDefinition / GameConfig (parsed once)
      ├─ Renderer (read-only game snapshot, GPU textures/instances)
      ├─ UILayer / AudioMixer (events and snapshot)
      └─ SaveRepository (schema and atomic write)
```

原则：单线程运行物理；**不为每砖建立实体或每球独立组件**。`core` 不依赖 SDL/GL。游戏数值来自 [`../assets/config/gameplay.json`](../assets/config/gameplay.json)，关卡来自 [`../assets/levels/`](../assets/levels/)，规则详见 [`12_CORE_ALGORITHMS.md`](12_CORE_ALGORITHMS.md)。

## 2. 组件边界与数据流

| 模块 | 可写数据 | 输入 | 输出 | 禁止行为 |
|---|---|---|---|---|
| `ConfigLoader` | 只读 GameConfig | gameplay.json | 已验证参数 | 运行中隐式重置参数 |
| `LevelRepository` | 只读 LevelDefinition | Lxxx.json | 砖格、出生点、theme | 把 Tiled 结构暴露给物理 |
| `BrickField` | HP、目标计数 | `Hit(cell)` | 砖块变化、计分因子 | 逐格 new / GL 调用 |
| `BallPool` | 球位置、速度、活动标记 | 创建、回收 | ID 稳定活动索引 | 碰撞时分配对象 |
| `Simulation` | 球、挡板、砖 | 固定步、输入状态 | 物理碰撞结果 | 根据渲染 FPS 改变速度 |
| `GameSession` | 生命、分数、道具、状态 | 物理与输入事件 | 快照、音效/UI 事件 | 依靠 UI 自行扣 HP |
| `Renderer` | GPU 纹理、VBO | 只读快照 | GL 帧 | 修改游戏规则或随机增球 |
| `SaveRepository` | 本地保存数据 | 最佳成绩、设置 | 成功/失败结果 | 假成功、覆盖坏存档 |

内部模块接口的签名约定见 [`12_CORE_ALGORITHMS.md §7`](12_CORE_ALGORITHMS.md)。控制命令**独立于 fixedTick**；`FrameCollector` 每 tick 复制事件/状态，每显示帧返回拥有数据所有权的 `FramePacket`。`Renderer` 必须画 `BallRenderState`、`PaddleRenderState`、`ItemRenderState`，不得只画砖和球。

## 3. 物理实现约束

- 连续圆/矩形相交基于**边时间 + 四角二次求根**；网格先做扫掠 AABB 候选查询，提取最早接触时间，接触后消耗剩余物理子步。
- 同一时间组内按稳定种类和 CellIndex 顺序处理；单球一个接触组对一砖只扣一次 HP；所有球按稳定 BallId 升序执行，砖变化立即影响后续球。
- 24 次接触上限是数值容错保护，超过时不允许直接推进到可能穿墙的末点；错误归档到诊断日志。
- 挡板使用横向偏移控制出射角；其他碰撞做反射并标准化速率，且明确边界和球离屏回收规则。
- B 掉落、拾取、增球、同 tick 通关/丢命的确定顺序在算法规格中冻结，不能由 UI 动画回调驱动。

## 4. 渲染实现约束

V1.3.1 沿用原拟议的简单整图更新**收敛为简单可靠方案**：砖格固定 96×160，GPU `GL_RGBA8UI` 状态纹理仅 **61,440 字节**。仅当本渲染帧内砖块状态变化时，CPU 重建一次完整纹理并且最多上传一次；无变化不更新。将来根据真实数据再决定是否实现脏矩形。

弹球实例集中上传（最大 1,024）并批量绘制；挡板、掉落道具以 `PaddleRenderState`、`ItemRenderState` 值快照绘制，UI 按 SessionSnapshot 与 FramePacket.events 渲染。`Renderer` 不处理碰撞，不通过动画直接修改砖块数据。GL 上下文丢失后从 CPU 状态全量恢复。

Android 采用 GLES 3.0，桌面用 GL 3.3 Core；shader 用各自版本头并保持数据/效果一致，不要求 Windows 驱动暴露 GLES 环境。文本使用 SDL3_ttf 缓存字形；音频通过集中聚合接口播放，具体 SDL3 音频库的依赖版本在 T12 固定，不对每次碰撞独立启动声音。视觉资源参数唯一来源 [`visual.json`](../assets/config/visual.json)，详见 [`14_VISUAL_DESIGN_AND_FEEDBACK.md`](14_VISUAL_DESIGN_AND_FEEDBACK.md)。

## 5. 生命周期和构建边界

Android 以 SDL3 官方 Android 项目模板 + Gradle + NDK + CMake 接入；主要核心代码与 Windows 共用。系统退后台立即暂停物理/音频、清空时间累积器；前台先恢复 GPU 资源再允许继续。资源打进 APK；存档写应用私有目录。V1 不用 Docker、不联网、不集成云服务、广告、账号。

## 6. 工程目录和依赖

```text
MassBreaker/
├── CMakeLists.txt
├── android/                       # 官方 SDL3 Android 模板派生
├── core/include/massbreaker/      # 公共算法 API、配置、level、事件
├── core/src/{app,game,physics,grid,render,level,input,audio,save}/
├── desktop/
├── assets/{config,levels,shaders,audio,images,fonts}/
├── levels-src/                    # Tiled 源
├── tools/level-export/           # 导出 / 校验 / 预览
├── tests/unit/
└── docs/
```

构建与锁版本见 [`06_BUILD_AND_RELEASE.md`](06_BUILD_AND_RELEASE.md)；按 [`05_DEVELOPMENT_TASKS.md`](05_DEVELOPMENT_TASKS.md) 分阶段产出实际源代码。此文档仅为**可实现的工程接口与设计规格**，不是声称已存在上述目录的 C++ 源码。

## 7. 渲染帧交接与控制通道不可变约束（V1.3.1）

- 主循环先处理 SDL 系统事件与 UI 分层命中，再立即应用 `ControlCommand`；只有未暂停且前台时才允许向固定步发送 `GameplayCommand`。暂停、重试、恢复即使本显示帧执行 `0` 次物理步也必须生效。**每完成一个 fixedTick，必须重新判定 `phase()/isSimulating()` 与代际变化；进入 WON/LOST 或发生 PLAYING→READY 等转场，立即退出追赶循环并将 accumulator 归零。**不允许仅在 while 外判断一次。
- `FrameCollector` 每个物理 tick 从 `GameSession` **当场复制**砖块变化、排序事件和包含球/板/道具的完整 `RenderSnapshot`；不得跨 tick 缓存 `std::span`。显示帧结尾输出独立的 `FramePacket`，其中 `previousTick/currentTick` 是**相邻物理步**，不是相邻显示帧。**HUD 唯一路径 `frame.currentTick.hud`，没有 `frame.hud` 字段。**事件唯一枚举见算法 §7.1：含 `PaddleHit`，拾取一律叫 `ItemCollected`。
- 显示帧只有一次事件 drain；**零 tick 无新的物理事件，但控制命令可生成 `SessionReset`**，并在本帧更新 HUD／全量砖状态。N tick 一次性消费 N tick 的重要事件。砖块最终纹理只需当前全量 CPU 数据，最多每显示帧上传 1 次。复位/场景跳转/GL context 丢失后强制全量刷新并禁止跨场景插值；从固定步进入终态时必须保留终态事件，不得在清理插值时丢弃。

## 8. 公共 API 与任务验收边界（V1.3.1）

- 唯一事件列表为 `BrickHit/BrickDestroyed/PaddleHit/ItemSpawned/ItemCollected/BallsSpawned/BallLost/LifeLost/LevelWon/LevelLost/SessionReset`；其 `subjectId/value` 见算法 §7.1。接口不得自行扩展 `BonusCollected` 同义枚举。
- `ControlResult.events` 负责零物理步控制事件，`FrameCollector.onControlTransition(session,result)` 当场复制；物理转场使用 `onSimulationTransition(session)`，**保留刚复制的终态事件**。
- T10 的 UI 结构/行为独立验收，不包含 T11 的真实存档成功与 T12 的正式字体。T11 负责保存成功门槛，T12 在 T11 之后完成完整 UI 整体验收。详见 [05_DEVELOPMENT_TASKS.md](05_DEVELOPMENT_TASKS.md)。
