# 技术架构与工程接口

**编号：** MB-ARCH-003｜**决定：** C++20 + SDL3 3.4.20 + OpenGL ES 3.0（Android）/ OpenGL 3.3 Core（Windows）

## 1. 架构总览

```text
SDL3 Platform (window, touch, lifecycle, file/audio)
  └─ AppController (UI navigation, asset loading, fixed clock)
      ├─ FrameScheduler (event wait, display deadlines, refresh/present)
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
| `BrickField` | HP、`initialTargets`（本代际常量）与 `remainingTargets` | `Hit(cell)` | 砖块变化、计分因子 | 逐格 new / GL 调用 |
| `BallPool` | 球位置、速度、活动标记 | 创建、回收 | ID 稳定活动索引 | 碰撞时分配对象 |
| `Simulation` | 球、挡板、砖 | 固定步、输入状态 | 物理碰撞结果 | 根据渲染 FPS 改变速度 |
| `GameSession` | 生命、分数、道具、状态 | 物理与输入事件 | `SessionSnapshot`（含核心派生的 `destroyedTargets`）、音效/UI 事件 | 依靠 UI 自行扣 HP 或累计已毁砖 |
| `FrameScheduler` | 显示截止时间、平台等待/刷新率策略 | 前后台、输入待办、UI dirty/动画 | 阻塞唤醒、呈现时机 | 忙等、双重限帧、改变物理 dt |
| `FrameCollector` | 预分配快照/事件/CPU 砖图 | tick 输出、控制结果 | 同步只读 FramePacket 借用 | 每帧重分配、跨 release 保存引用 |
| `Renderer` | GPU 纹理、VBO | 只读快照 | GL 帧 | 修改游戏规则或随机增球 |
| `SaveRepository` | 本地保存数据 | 最佳成绩、设置 | 成功/失败结果 | 假成功、覆盖坏存档 |

`initialTargets` 在装载关卡时由 `BrickField` 统计并在本代际保持不变；`remainingTargets` 只在 HP 首次归零时递减；`GameSession::snapshot()` 派生 `destroyedTargets=initialTargets-remainingTargets`，通过 `frame.currentTick.hud` 供失败页和 HUD 使用。固定墙不计入目标，不建立 UI 侧事件累计器。V1 仅生命耗尽进入 `LOST`，固定显示“生命耗尽”。

模块表定义职责和所有权，不要求每行都独立成库、虚接口、注册器或工厂；仅在真实边界和测试替换需要时拆分。

内部模块接口的签名约定见 [`12_CORE_ALGORITHMS.md §7`](12_CORE_ALGORITHMS.md)。控制命令**独立于 fixedTick**；`FrameCollector` 持有可复用的 FramePacket，每 tick 将有效实体写入预分配快照并增量应用砖变化，消费时返回 const 引用；所有消费者在 releaseFrame 前同步结束。`Renderer` 必须画 `BallRenderState`、`PaddleRenderState`、`ItemRenderState`，不得只画砖和球。

## 3. 物理实现约束

- 连续圆/矩形相交基于**边时间 + 四角二次求根**；网格先做扫掠 AABB 候选查询，提取最早接触时间，接触后消耗剩余物理子步。
- 同一时间组内按稳定种类和 CellIndex 顺序处理；单球一个接触组对一砖只扣一次 HP；所有球按稳定 BallId 升序执行，砖变化立即影响后续球。
- 24 次接触上限是数值容错保护，超过时不允许直接推进到可能穿墙的末点；错误归档到诊断日志。
- 挡板使用横向偏移控制出射角；单轴普通碰撞翻转速度分量，角/合成法线使用通用反射及归一化。廉价排除后再求必要角根，保留所有并列候选与边界/回收语义。
- B 掉落、拾取、增球、同 tick 通关/丢命的确定顺序在算法规格中冻结，不能由 UI 动画回调驱动。

## 4. 渲染实现约束

砖格固定 96×160，GPU `GL_RGBA8UI` 状态纹理为 **61,440 字节**。收集器持有常驻 CPU 砖图，按 BrickChange.rgba 只覆盖受影响格；普通命中不扫描/重建整图。brickUploadRequired 为真时，每个实际显示帧最多直接整图上传一次；成功才清 dirty。加载/复位/GL 恢复全量同步，无变化不上传。局部上传优化由实际驱动测量决定。

球、道具、UI 几何与实例缓冲预分配并复用，按有效长度处理。字形图集预热，文字内容不变不重排；粒子与尾迹池按 visual.json 的总量/生命周期预算分配。无变化的静态页面不周期绘制，不用全屏多遍特效表现局部反馈。

弹球实例集中上传（最大 1,024）并批量绘制；挡板、掉落道具以 `PaddleRenderState`、`ItemRenderState` 值快照绘制，UI 按 SessionSnapshot 与 FramePacket.events 渲染。`Renderer` 不处理碰撞，不通过动画直接修改砖块数据。GL 上下文丢失后从 CPU 状态全量恢复。

Android 采用 GLES 3.0，桌面用 GL 3.3 Core；shader 用各自版本头并保持数据/效果一致，不要求 Windows 驱动暴露 GLES 环境。文本使用 SDL3_ttf 缓存字形；音频通过集中聚合接口播放，具体 SDL3 音频库的依赖版本在 T12 固定，不对每次碰撞独立启动声音。视觉资源参数唯一来源 [`visual.json`](../assets/config/visual.json)，详见 [`14_VISUAL_DESIGN_AND_FEEDBACK.md`](14_VISUAL_DESIGN_AND_FEEDBACK.md)。

## 5. 生命周期和构建边界

Android 以 SDL3 官方 Android 项目模板 + Gradle + NDK + CMake 接入；主要核心代码与 Windows 共用。系统退后台立即暂停物理/音频、停止 GPU 提交和游戏帧定时、清空时间累积器；前台先恢复 GPU 资源再允许继续。资源打进 APK；存档写应用私有目录。V1 不用 Docker、不联网、不集成云服务、广告、账号。

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

## 7. 控制、快照与模块交接

- AppController 先处理系统事件和 UI 命中，再立即分发控制命令；PLAYING 命令在固定步消费，READY 有输入时只执行一次准备步、空闲不 tick。每步后检查状态和代际变化；转场停止追赶。追赶预算和 SafePause、Resume 的完整时钟规则见 [算法 §3](12_CORE_ALGORITHMS.md)。
- FrameCollector 将每个 tick 的有效实体写入复用快照，事件有序追加、砖图增量写；同步消费者每次借用只消费事件一次；HUD 路径为 `frame.currentTick.hud`。控制命令在零 tick 帧也可产生 `SessionReset`。物理终态事件必须保留，新会话丢弃旧代际瞬态事件；插值只使用同一会话的相邻物理步。
- 公共事件与字段唯一声明见 [算法 §7](12_CORE_ALGORITHMS.md)。`ItemCollected` 表示拾取，`BallsSpawned.value/overflowScore` 表示实际奖励；新球当步计入存活数，下一步才运动。渲染与 UI 不另建规则计数器。
- 场景复位或 GL 上下文恢复需要全量砖纹理；所有 GPU 资源从 CPU 当前状态重建。
- UI、存档和正式资源按 [任务表](05_DEVELOPMENT_TASKS.md) 分阶段验收；真机性能按 [测试规范 §5](07_TEST_AND_ACCEPTANCE.md) 判定。


## 8. 手机运行预算与调度职责

- FrameScheduler 是唯一等待/呈现负责人：游戏显示目标 60 FPS，120 Hz 物理在显示工作到期时批量推进；输入事件可以提前唤醒控制，但不自动触发额外物理或 GPU 提交。
- READY、菜单、暂停和终态在有限 UI 动画结束后阻塞等待。窗口暴露、保存完成和生命周期事件可唤醒；恢复不追赶静止时间。状态表及主循环以 [算法 §3.3](12_CORE_ALGORITHMS.md) 为准。
- Android 请求匹配游戏目标的显示刷新率，系统拒绝时仍限制应用提交并记录实际模式。Swappy/平台回退统一封装，禁止与另一套 sleep 限帧叠加；能力需按 Android API 级别检测。
- 稳态模拟、收集、实例构建不动态分配；活动球/道具有序增量维护，事件不整帧重排。临时借用、容量上界与释放规则见算法 §3.4/§7。
- 热状态变化优先降低可选视觉开销，不改变物理 dt 或球数。按 [QA §5](07_TEST_AND_ACCEPTANCE.md) 从 T08 采集轻量运行记录，T09/T12 检查新增负载，T16 验证持续运行；精确功耗按测量能力单列。
