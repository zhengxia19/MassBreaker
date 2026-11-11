# 核心算法与模块接口详细设计

**文档编号：** MB-ALG-012

**文档基线：** 当前规范，2026-11-11

**适用：** C++20 / SDL3 / Android GLES 3.0 / Windows OpenGL 3.3

**状态：** 规范已形成，可据此编码；**未经游戏运行和真机测试**。

## 0. 约束与权威来源

- 规则参数的唯一运行时来源为 [`assets/config/gameplay.json`](../assets/config/gameplay.json)。本文件描述算法、契约和单位，不允许在各模块重复硬编码另一套参数。
- 游戏世界固定 `24×40`；左上角 `(0,0)`，`x` 向右、`y` 向下；网格 `96×160`，格长 `0.25`。所有长度、速度、时间分别使用世界单位、世界单位/秒、秒。
- `core` 不依赖 SDL/GL；关卡资源从 [`04_LEVEL_DATA_SPEC.md`](04_LEVEL_DATA_SPEC.md) 的运行时 JSON 解码；渲染不拥有真实物理状态。
- V1 静态轴对齐砖/墙 + 圆形球 + 水平挡板；无球球碰撞、无移动/斜面墙、无穿透球、无额外物理引擎。
- **可复现的单线程更新**先于并行优化；不为 1024 容量目标预先引入线程池或 NEON。
- 手机低功耗是实现约束：按状态休眠、按显示截止时间调度、预分配并复用缓冲、有序数据增量维护、碰撞快速路径。实现直接遵循这些约束；测量用于验证效果和决定进一步取舍，不作为开始优化的前提。
- 物理仍固定 120 Hz、游戏显示目标 60 FPS；二者与线程唤醒频率分别定义。默认在显示工作到期时批量推进固定步，不为每个物理 tick 单独启动 120 Hz 定时器。

## 1. 参数表（由 gameplay.json 解析并验证）

| 常量 | 配置默认值 | 语义 |
|---|---:|---|
| `fixedHz` | 120 | 物理步长 `dt = 1/120 s` |
| `ball.radius` | 0.17 | 球半径（格长 0.25） |
| `ball.speed` | 18 | 发球、普通反弹后的恒定速率 |
| `ball.maxActive` | 1024 | 同局同时活动球硬上限；包括附着准备球 |
| `ball.minVerticalComponent` | 0.42 | 挡板回弹时垂直速度绝对值至少为 `0.42 × speed` |
| `paddle.centerY` | 38 | 挡板中心纵坐标 |
| `paddle.width/height` | 4.5 / 0.35 | 矩形碰撞区域 |
| `paddle.maxBounceFromUpDeg` | 65° | 挡板边缘的最大横向出射角 |
| `bonus.extraBalls` | +3 | 捡到 B 砖道具的增球数量 |
| `bonus.fallSpeed` | 6 | 掉落速度，忽略砖块与墙体 |
| `bonus.width/height` | 0.8 / 0.4 | 道具碰撞盒 |
| `bonus.fanAnglesFromUpDeg` | -18°、0°、+18° | 三颗新球初始方向 |
| `maxContactsPerBallStep` | 24 | 单球单步最多求解 24 次接触，超额记诊断事件 |
| `simulation.maxCatchUpStepsPerFrame` | 8 | 单个显示帧最多执行 8 个 fixedTick；有未完成积压则安全暂停 |
| `timeEpsilon` / `separationEpsilon` | `1e-5 s` / `1e-4` | 时间并列判定／接触推出距离 |
| `initialLives` | 3 | 单局生命数 |

数值为**首版锁定的设计默认值**；试玩平衡如需修改，改配置、更新用例并记录变更。不能依据这些数值声称实际通关时长已符合预期。

## 2. 核心实体与唯一数据所有权

```cpp
using BallId = uint32_t;
using CellIndex = uint32_t;

struct Vec2 { float x, y; };
struct BallState {
    BallId id; Vec2 pos; Vec2 vel;
    float radius; bool attached;
};
struct PaddleState { float centerX; }; // y、宽高从 GameConfig 读取
struct ItemState { uint32_t id; Vec2 pos; bool active; }; // V1 仅 +3
struct BrickCell {
    uint8_t type;      // EMPTY, NORMAL, HP2, HP3, WALL, BONUS
    uint8_t hp;        // WALL 永不减血，EMPTY=0
    uint8_t palette;   // 显示用，不能决定碰撞
    uint8_t flags;
};
```

- `BrickField` 按 `index = row*96 + col` 持有固定容量连续数组；只允许 `Simulation` 写入。装载关卡或 Retry 时计算不可变的 `initialTargets`（初始 HP>0 的 `1/2/3/B` 格数，固定墙 `#` 不计）；`remainingTargets` 在**砖从 HP>0 首次变为 0 时**减 1，HP>1 降为 HP>0 不减少目标数。`GameSession::snapshot()` 计算 `destroyedTargets = initialTargets - remainingTargets`，不维护第三份可变统计，也不允许 UI 累计 `BrickDestroyed` 事件代替权威值。
- `BallPool` 预分配 1024 槽、自由索引池和单调递增 `BallId`，维护按 ID 升序的紧凑活动索引表。tick 开始只记录活动表有效长度；遍历期间不移动索引。运动结束后标记并稳定压缩离场项，再把新球追加到表尾。新 ID 单调增加，即使复用低位槽也不改变 ID 顺序；无增删时不重建、不排序、不扫描全部空槽。新增球当步计入容量/HUD/存活数，下步才参与 CCD。
- 道具同样按单调 ItemId 追加、稳定删除；按有效长度遍历。事件由唯一序号生成器按 `(generation,tick,sequence)` 顺序追加；不对已经有序的整帧事件再次排序。Debug 验证单调性，不能靠排序掩盖顺序错误。
- `GameSession` 持有得分、生命、状态、道具队列、关卡编号和 RNG seed；`RenderSystem` 仅读取 `FramePacket`，绝不反向修改 `BrickField`。
- 道具 `ItemState` 上限建议 128，固定池；达到上限时作为开发诊断错误而非无提示吃掉奖励。设计期 30 关最多 40 个 B，正常不会达到该限制。
- **每次击中某砖只会导致一次 HP 变化**：对同一球在同一个接触组内去重；单次连续接触通过分离容差避免在下一次迭代再次扣血。球离开并重新撞到同一砖可再次造成伤害。

## 3. 固定步更新和精确事件顺序

### 3.1 游戏状态、两条命令通道与暂停不变量

`BOOT → HOME/SELECT → READY → PLAYING → {PAUSED | READY | WON | LOST}`。`isSimulating()` 仅在 `PLAYING` 且允许前台模拟时为真；`acceptsGameplayInput()` 在前台 READY/PLAYING 为真；`phase()` 返回状态枚举，供主循环判断每一次物理步后的转场。`PAUSED` 保存 `pausedFrom∈{READY,PLAYING}`。游戏 **状态机由 GameSession 管**；UI 的屏幕（Gameplay/Pause/Win/Lose 等）和 `ModalDialog` 另由 `AppController/UIController` 管，模态弹窗不属于模拟状态。

**控制通道 ControlCommand**（Pause、Resume、Retry、ExitToSelect、Confirm、Cancel、AppSuspend）在 `SDL_PollEvent` 之后、**每次显示循环的物理累积器之前**同步处理，即使没有任何 fixed tick 也会执行；所有转场输出新的 `SessionSnapshot.revision`。**玩法通道 GameplayCommand**（MovePaddle、Launch）在 PLAYING 的下一固定步采样；READY 只在有有效输入的显示工作中执行一次准备步。准备步使用同一个 `fixedTick(fixedDt,commands)` 入口，只更新挡板/附着球、消费 Launch，不执行球运动/CCD/道具下落；若发球，运动从后续 PLAYING tick 开始。READY 空闲不累积时间、不执行空 tick；同一显示周期内 MovePaddle 合并为最新映射位置，Launch 保留且最多消费一次。手势层仍记录整段最大位移，不能因合并移动事件误判轻点。PAUSED/模态出现时丢弃未执行命令。两种命令不可混用一个“等 fixedTick 才消费”的队列。

- `Pause`：若 READY/PLAYING，立即保存 `pausedFrom`、切 PAUSED（`pauseReason=User`）、清空累积器和玩法命令、取消触控捕获、暂停音频；本显示循环不再运行物理。
- `SafePause`：**仅 AppController 内部生成**，不暴露为 UI 按钮；当追赶预算耗尽且仍存在完整待执行 fixedDt 时立即生效：存储 `pausedFrom`、进入 PAUSED（`pauseReason=SimulationOverload`）、停止音频和 gameplay 命令、清零累积器，记录每次过载诊断（显示帧、积压步数、已执行步数），保留已经收集的有效 tick 事件和当前物理状态，不扣生命、不删球、不补算积压时间。暂停期间仍响应退出或重试。
- `Resume`：仅前台、PAUSED、无模态时有效；立即恢复 `pausedFrom` 并清除 `pauseReason`，清空累积器和玩法命令/手指捕获、重置单调帧时间基准；恢复到 PLAYING 后从**下一次累积满 dt**才再次 fixedTick；恢复到 READY 后等待有效输入，不启动周期物理计时。因过载安全暂停时也由用户**主动**点继续，不自动重试历史积压，若设备持续过慢允许再次安全暂停。无“先执行一轮物理才能恢复”的死锁。
- `Retry`：PAUSED 的确认框确认、WON/LOST 的重试按钮都可触发；在控制通道立即调用 `reset(currentLevel,config)`、恢复 READY/附着球、**sessionGeneration 递增、simTick 归零、revision 递增**、重新制作砖块全量渲染状态；不执行当前帧的物理补算。
- `ExitToSelect`：确认后退出至选择关卡，停止物理；系统 `AppSuspend` 立即 PAUSED（`pauseReason=AppSuspended`，如已暂停则保留原因）或保持终态，直到回到前台且用户主动点“继续”才允许恢复。
- **计数不变量（不允许重置混用）：** `simTick` 是**本代际内已完成的 fixedTick 数量**。初建会话计数为 `0`；每完成一个 fixedTick 增加 `1`；`Pause/Resume/AppSuspend/SafePause` 不改变它；`WON/LOST` 保留触发终态的最后 tick 值。`Retry`、新关卡装载创建**新会话**，应 `sessionGeneration += 1` 且 `simTick = 0`。首次会话从 `generation=1,tick=0` 开始；切换菜单但不建新会话不能虚增代际。
- `revision` 是**当前应用进程内单调递增**的 UI/状态版本号：每次实际状态转场、Retry、新会话装载或可见 HUD 数据变更时增加，暂停/恢复会增加，**绝不因为 Retry 清零**。单纯相同状态的无效控制不增加 revision。进程重启后允许从初始值重新计数，存档不持久化 revision。
- `OrderedEvent` 以 `(sessionGeneration,simTick,sequence)` 定位；同代际同 tick 内 sequence 唯一且递增。新会话复位前必须丢弃待显示的**旧代际瞬态事件**并禁止跨代际插值；只有新代际 `SessionReset` 被交付，暂停与恢复不清除本显示帧已经产生的有效物理事件。


### 3.2 每个 fixed tick 的权威顺序

本节步骤 3–8 的运动与终局逻辑仅用于 PLAYING。READY 准备步按 §3.1 更新挡板/附着球、处理 Launch 后提交快照并递增 simTick；不执行后续运动或补算静止时间。

1. **采样玩法输入**：只读取控制通道已确认允许运行时留下的 `MovePaddle/Launch`；Pause/Resume/Retry 早已由主循环的控制通道处理，绝不在此等待。
2. **更新挡板**：直接按照已映射的世界位置 clamp 到 `[width/2, 24-width/2]`；准备球随挡板水平移动。
3. **活动球运动**：使用 tick 开始时按 BallId 升序的快照逐球进行 CCD，每个有效砖块命中立即扣 HP，并更新 `remainingTargets/score`；产生 `BrickDestroyed` 记录。已归零砖块对后续球立即表现为空格。所有本步活动球运动结束后，统一提交离场球回收并释放槽位，供步骤 6 使用。
4. **本 tick 的新掉落道具入队**：B 砖刚摧毁产生道具；**从下一物理步开始下落**，避免刚生成就跨过碰撞区。
5. **更新既有掉落道具**：沿 y 轴正方向移动，检测与挡板矩形相交或离场；采集 `ItemCollected` 事件。
6. **消费已拾取道具**：按道具 ID 升序、每次申请新增 3 球，使用步骤 3 回收后的剩余槽位；**当步提交球池，立即计入容量、HUD 球数和步骤 7 的存活判定**。新球位置与方向固定，不参与本步已结束的运动遍历，**从下一物理步开始运动**。每次提交后再处理下一道具；上限不足时每少 1 球补 50 分并提示。
7. **统一终局判定（高优先级在前）**：`remainingTargets==0 → WON`；否则按步骤 6 提交后的球池统计存活数量（计入当步已生成、尚未运动的新球）；若数量为 0 且状态仍为 `PLAYING`，生命减 1，并进入 `READY` 或 `LOST`。即使道具还在空中也不延迟全失球判定。
8. **提交事件与快照**：把本步砖块变化、UI 提示、音频聚合事件交给只读渲染/界面；不在渲染时再次改变玩法。

**同一步 B 砖击破恰为最后目标**：直接赢，未收集的道具不再影响结果。**同一步最后一球掉落又接到增球**：先消费道具，存在新球则不扣生命。**同一步最后目标击破且最后一球掉落**：赢优先。

### 3.3 按状态与截止时间调度的主循环

`FrameScheduler` 是唯一等待和呈现节奏负责人。平台事件可提前唤醒以处理控制；提前唤醒不自动执行物理或提交 GPU 帧。PLAYING 到显示工作截止时间后，按真实 elapsed 累积并执行最多 8 个固定步，通常为每 60 Hz 显示周期 2 步。显示限帧不改变物理 dt。

| 状态 | 物理与输入 | 呈现与等待 |
|---|---|---|
| PLAYING | 120 Hz 固定步；到期批量执行；输入按捕获规则合并 | 目标 60 FPS，由单一帧节奏实现等待；不忙等、不无上限提交 |
| READY | 无输入时 0 tick；有输入时每显示周期最多一次准备步；不累计空闲时间 | 输入、窗口暴露或 UI 动画引起重绘；静止后等待事件 |
| HOME/SELECT/SETTINGS/TUTORIAL | 不运行游戏物理 | 交互或短动画时最高 60 FPS；动画结束后按需重绘 |
| PAUSED/WON/LOST | 不运行游戏物理；控制立即处理 | 场景冻结，有限的面板动画完成后停止周期绘制；窗口暴露/尺寸变化/恢复可触发重绘 |
| 后台/不可见 | 停止游戏 tick、呈现计时及游戏音频，不积累游戏时间 | 等待平台生命周期/必要完成通知；无游戏自建轮询定时器；不执行 GL 绘制/交换 |

显示截止时间由单调时钟和平台帧节奏统一计算；处理事件必须有批次上限并检查截止时间，不能被连续 MOVE 饿死。等待采用可被事件打断的阻塞机制（例如 SDL_WaitEventTimeout），不使用自旋或反复零超时轮询。音频播放可以有设备回调，但不能因此刷新静止画面；后台停止无用混音。静态页面允许系统自行合成已有画面。

Android 默认请求与 60 FPS 相匹配的显示模式，记录系统实际采用值；请求不被支持或未被采纳时仍限制应用提交到目标帧率。不能把 swap interval=1 等同于所有手机上的 60 FPS。帧节奏可接入 Swappy，由平台适配层统一所有呈现等待；不同时叠加另一套固定 sleep 限帧器。SDK/NDK 版本不支持的能力须功能检测和回退，实际接入在 T02/T07 验证。

**转场不变量**：每次 fixedTick 后重查 phase/generation；发球、失球复位、终态或代际变化立即结束追赶并清零 accumulator。控制转场即使零 tick 也更新 UI；转入新阶段不使用旧时间。下面是职责级伪代码，`work.frameDue` 是应用显示工作的截止时间，不等同于每一次系统 VSync 或输入事件。

```cpp
while (app.running()) {
    // 根据前台状态、当前页面、待处理输入/事件、UI dirty 与动画截止时间阻塞等待。
    // 窗口暴露、保存完成、生命周期事件也能唤醒；无待办时没有周期游戏唤醒。
    const auto work = scheduler.waitForWork(app, input, ui);
    ui.dispatchTopmostFirst(work.events);
    const auto control = app.dispatchControlCommands();
    const double now = monotonicSeconds();
    if (control.resetTimebase || !app.isForeground() || !session.isSimulating())
        accumulator = 0;
    else
        accumulator += std::max(0.0, now - lastClock);
    lastClock = now;

    if (work.frameDue && app.isForeground() && !control.resetTimebase) {
        if (session.phase() == GamePhase::READY && input.hasGameplayCommands()) {
            session.fixedTick(fixedDt, input.consumeForTick()); // 仅一次准备步
            frameCollector.captureTick(session);
            frameCollector.onSimulationTransition(session); // READY 不插值、不追赶
            accumulator = 0;
        } else {
            int steps = 0;
            while (session.isSimulating() && accumulator >= fixedDt &&
                   steps < config.simulation.maxCatchUpStepsPerFrame) {
                const auto before = session.phase();
                const auto generation = session.sessionGeneration();
                session.fixedTick(fixedDt, input.consumeForTick());
                frameCollector.captureTick(session);
                accumulator -= fixedDt;
                ++steps;
                if (session.phase() != before || session.sessionGeneration() != generation) {
                    accumulator = 0;
                    frameCollector.onSimulationTransition(session); // 保留末步事件
                    break;
                }
            }
            if (session.isSimulating() && accumulator >= fixedDt &&
                steps == config.simulation.maxCatchUpStepsPerFrame) {
                diagnostics.recordCatchUpOverload(steps, accumulator / fixedDt);
                const auto paused = session.applyControl({ControlCommand::Type::SafePause});
                frameCollector.onControlTransition(session, paused);
                input.cancelGameplayAndTouchCapture();
                audio.pauseSimulation();
                accumulator = 0;
            }
        }
    }
    const float alpha = session.isSimulating()
        ? std::clamp(float(accumulator / fixedDt), 0.0f, 0.999999f) : 0.0f;
    const FramePacket& frame = frameCollector.finishFrame(session, alpha);
    ui.consume(frame.currentTick.hud, frame.events);
    audio.consume(frame.audio, frame.events); // priorityEventIndices 仅在本次借用内有效
    renderer.consumeFeedback(frame); // CPU 反馈/复位同步消费；后台不积压瞬态效果
    if (app.isForeground() && work.frameDue && scheduler.needsPresent(session, ui)) {
        renderer.draw(frame);
        if (renderer.brickUploadSucceeded()) frameCollector.acknowledgeBrickUpload();
        scheduler.present(); // 只有这个呈现路径负责 pacing/交换
    }
    frameCollector.releaseFrame(); // 清事件有效长度，保留容量、快照、CPU 砖图和未上传 dirty
}
```

- `dispatchControlCommands()` 在每个命令处理后同步调用 `onControlTransition`；resetTimebase 包含 Pause/Resume/Retry/退出/前后台转场。准备步或控制修改使 UI dirty，并请求最近一个允许的显示截止时间；不依赖空 tick 或额外点击。一次已处理的变化不持续制造 dirty。
- PAUSED/终态帧可以更新面板与完成保存，但不推进场景动画。显示工作恢复后不追赶静止或后台时间；阻塞等待必须可被系统和用户事件唤醒。
- 仅 PLAYING 执行满预算且仍有完整 dt 才触发 SafePause；恰好 8 步无积压或已转场均不触发。过载清零累积器、保留已完成状态与事件并等待主动 Resume；不是常规节能策略。
- `needsPresent` 在 PLAYING 每个到期帧为真，在静态页面仅对 dirty/有效 UI 动画/系统重绘请求为真。GPU 纹理 dirty 直到成功上传才清除；未绘制的事件服务轮不能误清 dirty。窗口尺寸或 GL 恢复使页面 dirty 并请求全量上传。
- `simTick` 仍只计实际执行的 fixedTick；READY 静止不增长。每次有效准备步增加一次；Launch 准备步进入 PLAYING 后停止当轮更新，后续 PLAYING tick 才移动球。

### 3.4 复用快照、增量砖图与显示消费

`FrameCollector` 独占一个长期复用的 `FramePacket`，内含两个已预分配的快照缓冲、事件缓冲、音频摘要以及 61,440 字节 CPU 砖图。独立快照所有权用于隔离模拟数据，不要求每次创建新的堆对象。

1. 每个实际 tick 完成后，`captureTick` 交换 previous/current 缓冲，把活动球/道具有效前缀及挡板/HUD **写入一次** current 缓冲。保留相邻物理步，不把前一显示帧当作 previous。vector 保留 capacity，不执行 shrink_to_fit；静止零 tick 不重新复制实体数组。
2. `GameSession::tickOutput()` 返回其预分配临时缓冲的只读视图；有效期到下一次 fixedTick/reset/applyControl。收集器必须在这之前完成一次复制或增量应用，不保存指向模拟对象的 span。`ControlResult.events` 也必须当场消费。
3. 砖格变化时核心按 cell 编码最终 `[type,hp,palette,flags]`；本 tick 同格变化可用固定标记数组与 touched 索引合并。`BrickChange` 携带完整四字节状态。收集器仅覆盖 CPU 砖图对应四字节并置 `brickUploadRequired`；不扫描重建整图，不再把整图复制给临时 FramePacket。初次加载/Retry/换关和 GL 恢复才全量同步。
4. 事件由核心按顺序产生，收集器追加到已预分配的队列；不进行整帧排序。重要玩法事件完整交付，UI/声音/粒子消费者可以对纯反馈限流，但不得改变积分、目标或存档。音频 priorityEventIndices 使用事件索引，避免再复制整条事件。
5. `finishFrame()` 返回 `const FramePacket&`。所有消费者在同一线程同步完成，随后 `releaseFrame()` 清除事件和音频有效长度而保留容量；引用及其中 span 在 release 后失效，不能异步保存。释放不会清掉快照或未成功上传的砖图 dirty。若将来跨线程，须重新定义租约/多缓冲协议，不能直接复用这个借用接口。

`alpha=accumulator/fixedDt` 仅用于同一会话的 PLAYING 相邻 tick 插值。新实体直接画当前位、已删除实体不画；有序实体表可双指针合并 ID，不能逐球线性搜索另一份快照。READY/PAUSED/终态和任何转场禁止插值。HUD 唯一路径仍为 `frame.currentTick.hud`。

- 零 tick 控制也可产生 SessionReset；无物理更新时只更新 HUD/必要姿态。Retry/换关清除旧代际瞬态事件，以新会话填充两个快照并全量同步砖图。由物理进入 WON/LOST 必须保留终态事件。
- 无需绘制的控制服务轮仍处理 UI/保存状态并一次性消费事件；Renderer.consumeFeedback 同步处理 SessionReset/代际变化并清除旧尾迹，将需要的可见反馈写入自有有界池，不保留 FramePacket 引用。后台只采纳复位和状态，不排队等待前台重播音画瞬态。恢复显示时以当前快照重绘。
- T05/T07 在加载阶段根据关卡 HP 总量、球/道具容量、接触与追赶上限推导事件/变化缓冲的容量，记录总内存占用及容量计算；不得只给一个未验证的小常数。普通运行和压力回归中禁止热路径扩容。容量不满足已定义上界时初始化报错；运行中越界属于实现缺陷，不得静默丢事件或覆盖缓冲。
- 关键路径禁止临时 vector、逐事件字符串格式化和同步日志输出；诊断先写预分配计数/记录缓冲，在非热路径导出。加载、换关、资源重建和显式保存不计入稳态分配要求，须单独记录耗时。

## 4. 微型砖块候选查询

对球在剩余时间 `h` 内的移动，`p1=p0+v*h`。用扫掠矩形：

\[
A = [\min(p_{0x},p_{1x})-r,\max(p_{0x},p_{1x})+r]\times[\min(p_{0y},p_{1y})-r,\max(p_{0y},p_{1y})+r]
\]

加载时预计算 `invCellSize`，将扫掠范围映射并 clamp 到网格边界；按行列单次扫描覆盖格，空格立即跳过，不建立每球候选 vector、set 或哈希表。嵌套行列扫描天然不重复 cell；多来源接触用固定局部缓冲去重。只做一次最早 TOI 归并，再对最早并列组执行稳定优先级处理。

在当前速度 18、dt=1/120、半径 0.17 下，单个无反弹扫掠段在每轴长度不超过 0.49，通常最多覆盖 3×3 格；这是设计规模说明，不是忽略容差或参数变化的容量硬编码。候选缓冲边界按配置与容差推导，特殊恢复位置仍走完整检查。保留网格扫掠 AABB；空间树/DDA 只有在测量证实收益后再替换。

边界（左/右/上墙）、挡板也参与候选，但它们不是砖格目标。下方没有反弹墙，球完全离屏后回收。

## 5. 连续圆形与轴对齐矩形碰撞（CCD）

### 5.1 最早接触时间

输入 `(p, v, r, AABB, h)`，输出最早 `t ∈ [0,h]`、单位法线 `n`、碰撞类型，未命中返回 `none`。

**直边候选：** 计算球心到矩形四条边外侧偏移 `r` 的相遇时间，检查接触点对应的另一轴投影落在边线段内；仅接受 `v·n < 0` 的相向命中。

**四个角候选：** 对每个角 `c` 求解：

\[
\|p+vt-c\|^2=r^2,
\quad a=v\cdot v,\quad b=2(p-c)\cdot v,\quad d=(p-c)\cdot(p-c)-r^2
\]

判别式 `b²-4ad>=0` 时计算最早非负实根，并要求球心位于该角相应的外侧象限、`v·n<0`，法线 `n=normalize(p+vt-c)`。仅使用“把 AABB 四周扩大一个半径再做射线检测”会误判圆角，因此该办法**只能用于粗筛，不能作为最终命中法线算法**。

**求解开销控制：** 先做扫掠范围、接近方向与时间区间排除，只对仍可能进入最早接触组的角候选求二次根；必须保留 tMin+timeEpsilon 内的全部并列候选。已有直边命中不构成跳过所有角检查的理由。同一段复用速度平方/必要倒数；零速度分量显式分支。常量出生角正余弦加载时预计算，挡板变角只在实际碰撞时计算。快速路径使用可解析预期值及已有通用分支作对照，沿用同一容差；不为测试另建完整参考求解器。禁止 fast-math 改变判定。

**起点已重叠：** 若接触容差范围内，沿最小分离向量推出；球心在矩形内部时取最近面，四面同距离按固定优先顺序 `上→左→右→下`；不得按随机方向弹出。过深重叠要写诊断并恢复到该球上一有效位置。

### 5.2 最早碰撞与并列组

1. 从所有候选接触中取最小 `tMin`。
2. 把 `|t-tMin|<=timeEpsilon` 的接触组成一组，按 `kindPriority, cellIndex` 稳定排序（边界/固定墙优先于可破坏砖；挡板优先于砖）。
3. 组内可破坏砖**每格最多损伤一次**；按 cellIndex 升序处理命中和计分；墙永不扣 HP。
4. 若是挡板接触且球向下运动，**使用专用挡板出射**，不执行普通镜面反射；其余接触把相向法线相加后归一化得到 `n`，若因相互抵消长度接近零，选择 `-v·n` 最大的法线，完全并列按上述排序选第一条。
5. 单一轴向单位法线的普通接触直接翻转对应速度分量，保持速率，无需 normalize 或开方；挡板继续使用专用出射规则。角接触、非轴向合成法线使用 `v' = v - 2(v·n)n` 并归一到 ball.speed；严格保留并列组命中语义，不能把“碰到两个面”简化为错误的一次分量翻转。沿法线推出 separationEpsilon 防止零时长重复接触。
6. 从剩余 `h-tMin` 继续找下一个接触，最多 24 次；超限时将球停留在当前安全位置，输出诊断、跳过此球当前步的剩余极短时间，下一步继续恢复，不准穿过墙体。持续 3 个物理步超限时，恢复到上一无重叠位置、使用向上安全速度并记错误计数。

同一步允许同一球在**离开后重新接触**同一砖（例如高频腔体反弹）；在一个接触组内不重复。新球在道具结算阶段提交并计入当步存活数，下一步才加入运动遍历，不能改变本步活动球索引表。

### 5.3 挡板出射与边界

挡板中心 `px`，命中横向偏移系数：

\[
u=clamp((ball.x-px)/(paddle.width/2),-1,1),\quad
\theta=u\,65^\circ
\]

使用屏幕 y 正向朝下的坐标：`vx=speed*sin(theta)`、`vy=-speed*cos(theta)`。再保证 `vy<=-speed*0.42`（当前 ±65° 本身已足够满足，但保留作为规则保护）。挡板**仅接受由上往下命中其上表面**，禁止从挡板下方把球反射回场内。顶部墙：`y=r`；左右墙：`x=r, x=24-r`。当 `ball.y-r >=40` 时球已完全离屏并被回收；底边不是碰撞面。

## 6. 多球、道具和得分闭环

- 每一局准备状态只有 1 颗附着球。发球角度采用 `launchAngleFromUpDeg=0`，初始向上；以后反弹由角度控制。**不存在自动随时间增加弹球**。
- `B` 砖和普通砖一样 HP=1，摧毁时立即计 100 分，在该砖几何中心生成一个 `+3` 掉落物；`+3` 不与砖/墙碰撞，可穿过砖阵向下掉落，被挡板接到才生效。
- 拾取时在挡板上沿稍上方生成 3 球，水平位置偏移为 `-0.30 / 0 / +0.30`，与挡板不重叠，出射角 `-18/0/+18` 相对于竖直向上；若将来有特殊挡板宽度必须重新校验这组位置。生效顺序见 §3。掉落物在底边离屏后移除。
- 上限补偿：活动池容量剩余 `c`，新增 `min(c,3)`，未能新增的 `3-min(c,3)` 颗各补 `50` 分；对每个拾取发出一条 `BallsSpawned{subjectId=ItemId, value=actualSpawned, overflowScore=compensation}`，`actualSpawned` 即使为 0 也发事件，HUD 分数同步加入补偿；UI 唯一提示来源是该事件载荷。多次道具按稳定 ItemId 顺序应用。
- 计分只在砖块从 HP>0 变为 0 时一次性结算；按原始砖种 `1=100, 2=200, 3=300, B=100`；中途扣 HP 不另得分。
- 星级只根据通关时剩余生命：1→1星、2→2星、3→3星；失败不授星。最佳分与最佳星独立取最大值（可能来自不同局），这是有意定义。

## 7. C++ 模块接口（签名级契约）

**本节是唯一公共事件与帧数据字段定义（包含目标统计）**。`03_TECHNICAL_ARCHITECTURE.md`、`10_UI_UX_DESIGN.md`、`14_VISUAL_DESIGN_AND_FEEDBACK.md` 不得定义不同名称的重复类型；HUD 使用 `FramePacket.currentTick.hud`，事件统一使用 `ItemCollected`。

```cpp
using BallId = uint32_t;
using ItemId = uint32_t;
using CellIndex = uint32_t;
enum class GamePhase { READY, PLAYING, PAUSED, WON, LOST }; // 其余菜单由 AppController 管
struct ControlCommand {
    enum class Type { Pause, Resume, Retry, ExitToSelect, Confirm, Cancel, AppSuspend, SafePause };
    Type type;
};
// Confirm/Cancel 仅由 AppController 模态层消费并转换成 Retry/Exit 等；
// GameSession.applyControl() 不接收其模态命令本身。SafePause 仅 AppController 内部可发。
struct GameplayCommand {
    enum class Type { MovePaddle, Launch };
    Type type; float mappedWorldX;
};
struct BallRenderState { BallId id; Vec2 position; float radius; uint8_t style; bool attached; };
struct PaddleRenderState { float centerX, centerY, width, height; uint8_t style; };
struct ItemRenderState { ItemId id; Vec2 position; float width, height; uint8_t kind; };
enum class PauseReason { None, User, AppSuspended, SimulationOverload };
struct SessionSnapshot {
    uint64_t sessionGeneration, revision, simTick;
    GamePhase phase;
    PauseReason pauseReason; // 非 PAUSED 时为 None，PAUSED 时供 UI 区分过载/普通暂停
    uint32_t levelNumber; int lives, score, activeBalls, remainingTargets;
    uint32_t initialTargets, destroyedTargets; // GameSession 快照计算；不可由 UI 自行统计
    bool awaitingLaunch;
};
struct RenderSnapshot { // 收集器拥有；加载期 reserve，按有效长度复用
    SessionSnapshot hud;
    PaddleRenderState paddle;
    std::vector<BallRenderState> balls;
    std::vector<ItemRenderState> items;
};
struct BrickChange { CellIndex cell; std::array<uint8_t, 4> rgba; }; // 本 tick 最终状态
struct GameEvent {
    enum class Type {
        BrickHit, BrickDestroyed, PaddleHit, ItemSpawned, ItemCollected,
        BallsSpawned, BallLost, LifeLost, LevelWon, LevelLost, SessionReset
    } type;
    uint32_t subjectId; int32_t value;
    int32_t overflowScore = 0; // 仅 BallsSpawned 使用：容量不足的实际补分；其他事件必须为 0
};
struct TickOutputView { std::span<const BrickChange> changes; std::span<const GameEvent> events; };
struct ControlResult {
    bool stateChanged=false, levelReset=false, fullBrickUpload=false;
    std::span<const GameEvent> events; // 借用核心缓冲，下一次核心写操作前须消费
};
struct ControlDispatchResult { bool resetTimebase=false; }; // AppController 的本帧汇总
struct OrderedEvent { uint64_t generation, tick; uint32_t sequence; GameEvent payload; };
struct AudioSummary { int brickHitCount; std::vector<uint32_t> priorityEventIndices; };
struct FramePacket {
    RenderSnapshot previousTick, currentTick; // HUD: frame.currentTick.hud
    std::vector<OrderedEvent> events;         // 本显示帧一次性交付
    AudioSummary audio;
    std::array<uint8_t, 61440> fullBrickRgba; // 常驻 CPU 砖图，不按帧复制
    bool brickUploadRequired=false;        // 成功上传才清除
    float alpha=0;
    bool interpolate=false;
};
class GameSession {
public:
    GamePhase phase() const;
    uint64_t sessionGeneration() const;
    bool isSimulating() const; // 仅前台 PLAYING
    bool acceptsGameplayInput() const; // 前台 READY/PLAYING，仍受模态仲裁
    void reset(const LevelDefinition&, const GameConfig&);
    ControlResult applyControl(ControlCommand); // 允许没有 fixedTick
    void fixedTick(float dt, std::span<const GameplayCommand>);
    SessionSnapshot snapshot() const;
    void writeRenderSnapshot(RenderSnapshot& preallocatedOut) const;
    TickOutputView tickOutput() const; // 下一次核心写操作前有效
    void writeFullBrickRgba(std::span<uint8_t> out61440) const;
};
class FrameCollector {
public:
    void captureTick(const GameSession&); // 复用缓冲；立即消费 TickOutputView
    void onSimulationTransition(const GameSession&); // tick 转场；保留本 tick 事件
    void onControlTransition(const GameSession&, const ControlResult&); // 采纳控制事件
    void requestFullBrickUpload(); // GL 上下文恢复时调用
    const FramePacket& finishFrame(const GameSession&, float alpha); // 借用期间禁止核心更新
    void acknowledgeBrickUpload(); // GPU 成功上传后清 dirty
    void releaseFrame(); // 结束本次借用，清事件有效长度，不释放容量
};
class Renderer {
public:
    void consumeFeedback(const FramePacket&); // 不调用 GL；反馈进入有界自有状态
    void draw(const FramePacket&); // 不拥有 present/交换节奏
    bool brickUploadSucceeded() const; // 每次 draw 重新置值，无上传或失败均为 false
    void onContextRecreated();
};
```

### 7.1 事件清单、产生条件及载荷（唯一命名）

| 事件 | 产生条件 | `subjectId` | `value` |
|---|---|---|---|
| `BrickHit` | 砖 HP 有效减少一次（包括本次归零） | `CellIndex` | 新 HP；归零为 0 |
| `BrickDestroyed` | HP 首次降为 0 | `CellIndex` | 本次增加的分数 |
| `PaddleHit` | 球由上方有效撞击挡板并反射 | `BallId` | 0；同一接触组仅一次 |
| `ItemSpawned` | B 砖销毁并产生掉落牌 | `ItemId` | 3（可获得球数） |
| `ItemCollected` | 挡板拾取掉落牌 | `ItemId` | 3（请求新增球数） |
| `BallsSpawned` | 拾取处理完成，即使实际新增为 0 也发出 | `ItemId` | 实际生成数 0..3；`overflowScore=(3-value)*50` |
| `BallLost` | 单颗球从底边离屏、回收 | `BallId` | 0 |
| `LifeLost` | 本次生命最后一球丢失且无新球补充 | 0 | 扣命后剩余生命 |
| `LevelWon` | 最后目标砖摧毁，终态胜利 | 0 | 按剩余生命获得的星数 |
| `LevelLost` | 生命耗尽且未赢 | 0 | 0 |
| `SessionReset` | 控制通道确认重试/装载新会话 | 0 | 0 |

- `GameEvent::Type` 以本表的事件语义为契约。`ItemCollected` 在单一事件名称下承担拾取；不得新增同义名 `BonusCollected`。`PaddleHit` 是纯反馈事件，不允许根据 UI 动效再次改变物理方向。
- `BrickHit` 在打击后 HP=0 时仍会发生；视觉仅对 `value>0` 使用“受损高亮”，`BrickDestroyed` 专门处理归零破碎。**`ItemCollected` 仅代表拾取成功并消失，不直接显示“+3球”**；紧随其后的同 ItemId `BallsSpawned` 表达本次实际奖励：`value` 为实际新增 0..3，`overflowScore=(3-value)*50` 已由 `GameSession` 写入总分，UI 按这**两个事件载荷字段**生成提示，不通过 HUD 总分差额反推，不伪造三球全部生成。其他事件的 `overflowScore` 必须为 `0`。
- `SessionSnapshot` 的 `initialTargets` 在同一代际固定；`destroyedTargets = initialTargets - remainingTargets`，计算前须保证 `0 <= remainingTargets <= initialTargets`。V1 唯一玩法失败原因是生命耗尽（`LOST`），失败页显示固定文案 `生命耗尽`；其他资源读取或构建错误走非游戏失败提示，**不**推测为 LOST。未来增加其他玩法失败原因时，先扩展核心 `FailureReason` 接口及测试，不能让 UI 根据显示事件猜测。
- `OrderedEvent` 的代际、tick、顺序号来自唯一递增序号生成器；控制事件在 0 tick 情况下仍带当前 `sessionGeneration/simTick` 与唯一 `sequence`。`Retry` 后新代际从 `simTick=0` 开始，`revision` 持续递增；旧代际瞬态事件在重置时清除。同一事件交给一显示帧后不得重复交付。
- `AppController` 负责输入命令仲裁，`GameSession` 唯一写玩法数据；`FrameCollector` 在自有缓冲中收集独立快照和事件副本，`Renderer/UILayer/AudioMixer` 均不持有 `GameSession` 的可变引用。上层调用统一为 `ui.consume(frame.currentTick.hud, frame.events)`，禁止 `frame.hud` 或另设 `HudSnapshot` 重复来源。


## 8. GPU 合约与低复杂度实现

- GPU 状态纹理为 `96×160×4=61,440 bytes`。CPU 常驻砖图按 cell 增量写，`brickUploadRequired` 为真时直接上传一次整图；每个实际显示帧最多一次 glTexSubImage2D，无变化不上传。全量上传与 CPU 全量重建是两个不同操作，正常命中不重建整图。局部上传、PBO 或更多 GPU 缓冲只在测量证实收益后引入。
- 纹理内部格式选 `GL_RGBA8UI`，上传格式 `GL_RGBA_INTEGER/GL_UNSIGNED_BYTE`，着色器以 `usampler2D` + `texelFetch` 读取整数通道 `[type, hp, palette, flags]`；只允许最近邻采样，不使用插值，坐标与碰撞网格一一对应。
- 实例球体通过 1 次 `glBufferSubData`（或同等级批量写入）上传活跃球实例，按一次或少量批次绘制；**不逐球 Draw Call**。球视觉半径与物理半径一致，额外尾迹独立处理，不参加碰撞。
- Android GLES 3.0，Windows GL 3.3 Core；`#version 300 es` 和 `#version 330 core` 两个 shader 头；业务渲染路径保持一致。
- 上下文丢失时销毁 GPU 句柄并从 CPU `BrickField` 全量恢复。UI 对齐可视区域，而非重设世界/关卡坐标。
- 游戏帧、UI 几何、球实例与文字缓冲复用；文本只在内容/字号/颜色等改变时重排，字形图集在加载或界面切换时预热。高频 HUD 数字复用已有字形，静态控件不重复构造几何。
- 已启用的粒子组、每组粒子、存活时间、球尾迹点数使用 visual.json 的上限，预分配；可选尾迹未启用时不建立其池和更新路径；关闭效果时停止对应更新/实例上传。绘制限制在实际可见世界/UI 区域，合并相同材质，控制透明重叠，不以全屏后处理实现局部命中闪光。显示分辨率调整需验证微砖/球的可辨识性，不能自动损坏读图能力。
- 声音按显示帧最多合并播放配置指定的击砖音效数量（默认 4），优先增球/通关/失球；预加载采样，不在碰撞时解码或启动文件 I/O。静音/后台时停止无用混音，播放状态与画面调度分离。反馈限流不影响规则事件。
- 热状态监听是事件驱动的；热压力上升先关闭可选尾迹/减少粒子与光晕，保证核心球/砖清晰。V1 不自动改变物理 dt、删除有效球或把正常游戏改成频繁 SafePause；若基础画质仍不能达到验收门槛，记录不通过。

## 9. 输入、适配与持久化

- SDL 触屏指针捕获 finger ID；优先级 **系统挂起/焦点事件（禁止游戏操作）→ 模态对话框 → 暂停面板／页面导航 → HUD 暂停按钮 → 挡板控制区**。模态出现先取消旧手指捕获，抬起不得穿透发球。已捕获手指的位移映射为世界位移，第二手指不抢占。
- Android 返回键在模态时仅取消当前模态；否则在游戏时暂停、暂停时恢复、其他菜单按导航栈回退。暂停和重试控制命令按 §3.1 由显示循环处理，**不等物理 tick**。
- READY 状态下，控制区一次轻点（按下到抬起移动小于 `8` UI 单位）发球；滑动只移动挡板，不误触发球；外部 UI 点击不发球。
- 物理逻辑世界使用 `WorldViewport` 等比缩放，无视物理单位的 DPI；UI 使用安全区和 360×800 参考坐标。前后台切换立即暂停，不补算离开期间时间。
- 存档格式采用有 `schemaVersion` 的 JSON，储存 `bestScore/bestStars/unlockedLevelId/settings`；不存储进行中的物理快照。新文件先写临时文件、刷新后再替换，保留最近可读的备份。存档失败时不显示“成功保存”，提供重试。

## 10. 错误与不变量

| 不变量 | 断言/处理 |
|---|---|
| `0 ≤ activeBalls ≤ 1024` | 新球容量受控，超过上限按积分补偿 |
| `0 <= remainingTargets <= initialTargets` | `initialTargets` 从关卡 HP>0 目标格初始化（排除墙）；仅 HP 首次归零减剩余目标，不能负数 |
| `destroyedTargets == initialTargets - remainingTargets` | 仅由 `GameSession::snapshot()` 派生，Retry/下一关重新按新代际计算；不可维护第三份计数 |
| 所有活动球位置速度为有限数 | 非有限输入或求解输出：记录错误并恢复最近稳定状态 |
| 坐标与目标配置一致 | 导出/加载两端校验；资源版本不符拒绝加载 |
| 玩法事件在同一 tick 顺序稳定 | 球 ID + CellIndex + ItemId 三重稳定顺序 |
| Renderer 不修改砖或球 | 状态唯一路径：GameSession/Simulation |
| READY 必有且只有一颗附着球 | 全失球扣生命后重建，不带入上一生命的道具 |
| 不创建球球碰撞事件 | V1 无球球碰撞，球可互相穿越 |

## 11. 随实现验证的算法行为

以下 ID 标识覆盖要求，不代表必须分别编写独立测试或验收报告。同一场景可以同时验证多个 ID；失败输出须能定位断言。接口字段和枚举使用由正常目标编译覆盖，不另设字段拼写、成员不存在或枚举数量测试。

| 共用测试场景 | 覆盖要求 | 需保留的检查 |
|---|---|---|
| 两球击中同一 1HP 砖 | ALG-07、STAT-03 | 一次销毁、一次加分、一次目标计数变化 |
| 容量余量 0..3 时拾取 | ALG-09、BONUS-01 | 新增球数、补分、事件与 UI 提示；UI 只补消费层检查 |
| 前后台暂停与恢复 | ALG-12、CTRL-03、PERF-03 后台部分 | 不追赶、未 Resume 不运动、后台无 GPU 提交 |
| 多 tick 砖变化与零 tick 服务轮 | FRAME-01、PERF-07 | 末态 HP、一次上传、未上传 dirty 保留、事件只交付一次 |
| 相邻快照与零 tick 重绘 | FRAME-02、PERF-08 | 插值正确、缓冲复用、借用生命周期；复位用例另检查代际 |
| READY 空闲后发球 | LOOP-04、PERF-01 | 单次准备步、无空闲追赶、无周期绘制 |
| 终态截断追赶 | LOOP-01..03、LOOP-07 | 按状态和积压量参数化，保留终态优先于过载的断言 |

单元测试中的长时间空闲使用可控时钟推进；真机生命周期与阻塞等待仍做集成检查，不要求每个单测实际等待 15 或 60 秒。

| 用例 | 关键输入 | 必须输出 |
|---|---|---|
| ALG-01 | 正向打到 1HP 砖 | HP=0，目标-1，计分一次 |
| ALG-02 | 同一个接触组碰到两个砖角 | 两砖各扣一次，法线确定 |
| ALG-03 | 高速越过厚度 0.25 的砖 | 不穿砖，命中最早接触 |
| ALG-04 | 球从角外掠过、未达到圆角半径 | 不误判撞角 |
| ALG-05 | 同步命中墙和砖 | 按法线/砖序规则稳定，墙 HP 不变 |
| ALG-06 | 一 tick 内多次撞墙 | 时间被正确消费，无无限反射 |
| ALG-07 | 两球同 tick 命中仅剩 1HP 砖 | 砖只销毁一次，积分只加一次 |
| ALG-08 | B 砖销毁且拾取 | 同步生成道具，拾取当 tick 提交 3 球并更新 HUD/存活数，新球位置在该 tick 保持出生点，下一 tick 才运动 |
| ALG-09 | 1023/1024 球时拾取 +3 | 只能加 1/0 球，分别补 100/150 分 |
| ALG-10 | 最后一球丢失且拾取 +3 | 离场回收后当 tick 提交 3 球，activeBalls=3、生命不变，不产生 LifeLost/LevelLost；新球当 tick 不运动，下一 tick 才运动 |
| ALG-11 | 最后一目标销毁且所有球丢失 | 赢优先，星级按剩余命数 |
| ALG-12 | 失焦/暂停后恢复 | 无后台物理补帧；球不跳跃 |
| ALG-13 | 读取损坏或不兼容关卡 | 可定位错误，安全返回菜单 |
| ALG-14 | 任意 N 个 B 都未拾取 | 多球不凭空出现，失球规则准确 |

测试重点是算法**行为与可复现性**，不是要求每一个边角场景都做性能调研。实现 T06 与 T09 时完成对应单元测试，T15 再做实际关卡试玩。

## 12. 控制、渲染与优先级回归用例

| 测试 ID | 场景 | 必须结果 |
|---|---|---|
| CTRL-01 | 进入 PAUSED，无 fixedTick；注入重绘后点 Resume | **立即**切回原 READY/PLAYING，下一轮按新时间基准累积，不出现控制死锁 |
| CTRL-02 | PAUSED 中点击 Retry，确认模态出现，再选择确认 | 不执行物理即可重建关卡、进入 READY，生命/砖格重置，`revision` 更新 |
| CTRL-03 | 后台暂停 15 秒，回前台点 Resume | 没有 15 秒的追赶 tick，不跳球；前台未 Resume 时仍冻结 |
| CTRL-04 | 原有拖动中触发确认模态，之后抬手 | 模态吃掉事件，不发生 `Launch` / 挡板继续拖动 |
| CTRL-05 | 模态打开时点其下方 HUD 暂停按钮 | 模态优先，底层按钮不触发；Back 仅取消模态 |
| FRAME-01 | 同一显示帧运行 3 个 fixedTick，每次砖受损 | GPU 当前纹理为最后 HP，最多一次整图上传，UI事件按 tick 升序逐条一次消费 |
| FRAME-02 | 球在两个连续物理 tick 间移动，显示帧 0 tick | 仍使用相邻物理 tick 快照插值，不用上次显示帧的位置 |
| FRAME-03 | 某 tick 增 3 球、移除 1 球和出现掉落物 | 新球／新道具画当前位，消失球不画；挡板位置可正确插值 |
| FRAME-04 | 注入 60 次窗口暴露事件，使暂停场景重绘 60 次 | 无重复砖击声、无重复 `ItemCollected`，球、板、道具不变化 |
| FRAME-05 | GL 上下文恢复或 Retry 后第一帧 | GPU 全量刷新砖图，上一关的球/道具不出现、不插值跨场景 |

对应实现任务 **T04/T07/T10**，测试随模块开发提交；这里是设计用例，尚未执行 C++ 测试。


## 13. 主循环终态与公共接口回归用例

| ID | 输入条件 | 预期与明确边界 | 任务 |
|---|---|---|---|
| `LOOP-01` | 累积器含 5 个 dt，第 2 tick 击破最后目标进入 `WON` | **只调用 2 次 fixedTick**；第 2 步的 `LevelWon` 事件交付一次；余时归零；下一显示帧 0 物理步 | T04/T06/T08 |
| `LOOP-02` | 累积器含 5 个 dt，第 2 tick 失去最后一命进入 `LOST` | **只调用 2 次 fixedTick**；`LifeLost/LevelLost` 各交付一次，无后续动作；余时归零 | T04/T06/T08 |
| `LOOP-03` | 累积器含 5 个 dt，第 2 tick 最后一球离屏且仍有生命，`PLAYING→READY` | 停在第 2 tick，READY 附着球快照正确，剩余追赶时间归零；不能用同帧旧输入再发球 | T04/T06 |
| `LOOP-04` | READY 空闲后接到 Launch | 到期显示工作仅执行一次准备步，球仍在发射点且转 PLAYING；不补算空闲时间；下一周期按新时钟执行运动 tick | T04 |
| `FRAME-06` | PAUSED 中控制通道 Retry，显示帧 0 fixed tick | `frame.currentTick.hud` 为重置后状态；events 恰有新代际 `SessionReset`，全量砖纹理已提供；下一帧不重复 | T04/T07 |
| `API-02` | 完成真实挡板反射、拾取 +3、场景重试 | 分别按载荷定义产生 `PaddleHit`、`ItemCollected`、`BallsSpawned`、`SessionReset`，不定义同义拾取事件 | T06/T09/T10 |

**注意**：这些是必须随对应 C++ 代码提交并执行的测试规格；当前项目不含可执行 C++ 引擎，不能把设计用例计为已通过。

## 14. 追赶预算、会话计数与奖励回归（T04/T09/T10）

| ID | 输入与条件 | 预期 |
|---|---|---|
| `LOOP-05` | PLAYING 有 20×fixedDt 积压、没有终态转场、预算 8 | 本显示帧**仅执行 8 次** fixedTick；同帧进入 `PAUSED` 且 `pauseReason=SimulationOverload`；余时清零、当前帧已发生事件交付一次；Resume 后从新时间基准继续，不补算历史 12 tick |
| `LOOP-06` | 恰好 8×fixedDt 积压、预算 8 | 执行 8 步，积压小于 dt，继续 PLAYING；**不得误触发安全暂停** |
| `LOOP-07` | 第 2 步 WON / LOST / PLAYING→READY，预算 8，积压 20 步 | 仅 2 次 fixedTick、先终态截断、清空余时，**不记录过载**，保留终态事件 |
| `LOOP-08` | generation=7, simTick=27, revision=81 → Pause → Resume → Retry | Pause/Resume：gen 7、tick 27 不变，revision 增加；Retry：gen 8、tick 0、revision 单调增加；新代际只有 `SessionReset`，没有旧代际瞬态事件 |
| `LOOP-09` | SafePause 后注入重绘，0 fixedTick，用户未 Resume | 球/砖/计分不变，过载面板持续展示；不自动恢复、不重发事件 |
| `BONUS-01` | 接到一张 +3 道具，容量余量依次为 3、2、1、0 | `BallsSpawned.value` 依次为 3/2/1/0、`overflowScore` 依次为 0/50/100/150；提示 `+3 球` / `+2 球 · +50 分` / `+1 球 · +100 分` / `球数已满 · +150 分`，HUD 球数/积分匹配 |
| `BONUS-02` | 两张道具同 tick 拾取，容量仅余 4 | 先按 ItemId 处理一张加 3、下一张加 1 并补 100；每张各一条 `BallsSpawned`；不得合并为虚假的 `+6 球` |

这些是设计验收规格，**并非已经执行的 C++ 单元测试**。`simulation.maxCatchUpStepsPerFrame` 须按正整数解析并检查范围 `1..16`；默认配置为 8。不会因为性能下降而自动倍增 `fixedDt` 或悄悄丢弃游戏碰撞。

## 15. 目标统计与结算页回归（T05/T07/T10）

目标统计与失败文案契约见 §2、§7.1；以下用例验证核心派生值及 UI 消费结果。

| 回归 ID | 输入 | 预期 | 实现任务 |
|---|---|---|---|
| `STAT-01` | 初始 10 个可破坏砖（含两块 HP2）和 5 块固定墙 | `initialTargets=10, remainingTargets=10, destroyedTargets=0` | T05/T07 |
| `STAT-02` | HP2 砖第一次有效命中；随后第二次命中归零 | 第一次 10/10/0；第二次 10/9/1；`BrickDestroyed` 仅一次 | T05/T07 |
| `STAT-03` | 两球同 tick 对同一 1HP 砖命中 | 仅一次目标计数变化，`destroyedTargets` 增 1 | T06/T07 |
| `STAT-04` | 已破坏 3 块时 Retry，再加载不同目标数下一关 | Retry 新代际三项回到初始；下一关按其真实目标数重新初始化；旧事件不影响 UI | T04/T07/T10 |
| `STAT-05` | 最后一命丢失进入 LOST | 失败页读取同一快照的 `score/initialTargets/destroyedTargets`，失败文案为 `生命耗尽`，不重复累计事件 | T08/T10 |

上述为 **C++ 待实现测试规格**，尚非运行通过证明。


## 16. 低功耗与缓冲复用验收用例

以下是实施规格，不是实测结果；T04/T05/T06/T07 随模块完成，T08/T09 采集轻量运行记录，T12 检查正式效果，T16 完整验收；有重大性能改动时提前测量。

| ID | 输入或场景 | 必须结果 | 任务 |
|---|---|---|---|
| PERF-01 | READY 静止 60 秒后拖动/轻点 | 静止时 0 tick、无周期 GPU 提交；拖动到期一次准备步，Launch 不补算 60 秒，手势不误判 | T04/T10 |
| PERF-02 | 暂停/菜单/结算动画结束；随后窗口暴露或保存完成 | 静止时无周期游戏唤醒/呈现；系统事件可唤醒并按需刷新，控制不依赖绘制 | T04/T07/T10 |
| PERF-03 | PLAYING 输入事件频繁；90/120 Hz 屏；切后台再恢复 | 应用目标仍为 60 FPS，不因输入或屏幕频率超额提交；无自旋/双重限帧；后台 0 tick/0 GPU 提交，恢复不追赶 | T02/T04/T07 |
| PERF-04 | 预热后 1、121、1024 活动球及连续碰撞/拾取 | 核心模拟/收集器/实例构建稳态 0 堆分配/释放；容量有上界推导，不扩容、不丢事件；记录第三方分配与加载例外 | T05/T07/T09 |
| PERF-05 | 低位槽反复回收、新球/道具增加；多 tick 事件 | ID 顺序稳定、无整表重排序；事件单调完整；与确定输入的预期事件/状态相同，不要求另建回放系统 | T05/T09 |
| PERF-06 | 单轴墙/砖、角擦过、并列组、零速度分量、反复反弹 | 用可解析预期值及已有通用分支验证接触/HP/积分；不遗漏并列候选；轴向反弹不额外开方归一化；不另建参考引擎 | T06 |
| PERF-07 | 连续两个 tick 修改同格；夹入零 tick 控制轮 | CPU 只更新 touched 格；最新 RGBA 正确；无临时整图复制；未绘制不清 dirty，成功上传才清；复位/GL 恢复全量同步 | T07 |
| PERF-08 | 3 tick 后 finish/release，再零 tick 重绘及复位 | 最近两个相邻快照正确、容量/地址按交换规则复用；借用不过期使用；release 不抹掉状态，无事件重复 | T07 |
| PERF-09 | 密集命中、关闭效果/静音、切后台 | 粒子/尾迹不超配置预算；无重复文字重排、音频解码或无用后台更新；权威事件不减 | T12 |
| PERF-10 | 注入热状态/能力不可用；真机核验可用接口 | 支持时事件驱动降低可选效果；不支持时正常基础功能；不更改玩法 dt/球数；记录热稳态与功耗 | T07/T12/T16 |

功耗比较、长时间热稳定性及设备测量边界见 [验收规范 §5](07_TEST_AND_ACCEPTANCE.md)。
