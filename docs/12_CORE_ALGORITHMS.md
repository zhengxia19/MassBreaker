# 核心算法与模块接口详细设计

**文档编号：** MB-ALG-012  
**版本：** V1.3.1（终态追赶控制与接口一致性修订）  
**适用：** C++20 / SDL3 / Android GLES 3.0 / Windows OpenGL 3.3  
**状态：** 规范已形成，可据此编码；**未经游戏运行和真机测试**。

## 0. 约束与权威来源

- 规则参数的唯一运行时来源为 [`assets/config/gameplay.json`](../assets/config/gameplay.json)。本文件描述算法、契约和单位，不允许在各模块重复硬编码另一套参数。
- 游戏世界固定 `24×40`；左上角 `(0,0)`，`x` 向右、`y` 向下；网格 `96×160`，格长 `0.25`。所有长度、速度、时间分别使用世界单位、世界单位/秒、秒。
- `core` 不依赖 SDL/GL；关卡资源从 [`04_LEVEL_DATA_SPEC.md`](04_LEVEL_DATA_SPEC.md) 的运行时 JSON 解码；渲染不拥有真实物理状态。
- V1 静态轴对齐砖/墙 + 圆形球 + 水平挡板；无球球碰撞、无移动/斜面墙、无穿透球、无额外物理引擎。
- **可复现的单线程更新**先于并行优化；不为 1024 容量目标预先引入线程池或 NEON。

## 1. 参数表（由 gameplay.json 解析并验证）

| 常量 | V1.3 值（沿用 V1.2 数值） | 语义 |
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

- `BrickField` 按 `index = row*96 + col` 持有固定容量连续数组；只允许 `Simulation` 写入。`remainingTargets` 在**砖从 HP>0 变为 0 时**减 1。墙从不进入目标数。
- `BallPool` 预分配 1024 槽、自由索引池和单调递增 `BallId`；**每个 fixed tick 开始**生成按 ID 升序的活动索引表。移除／新增球只在指定阶段提交，不允许在遍历容器时导致索引失效。
- `GameSession` 持有得分、生命、状态、道具队列、关卡编号和 RNG seed；`RenderSystem` 仅读取 `FramePacket`，绝不反向修改 `BrickField`。
- 道具 `ItemState` 上限建议 128，固定池；达到上限时作为开发诊断错误而非无提示吃掉奖励。设计期 30 关最多 40 个 B，正常不会达到该限制。
- **每次击中某砖只会导致一次 HP 变化**：对同一球在同一个接触组内去重；单次连续接触通过分离容差避免在下一次迭代再次扣血。球离开并重新撞到同一砖可再次造成伤害。

## 3. 固定步更新和精确事件顺序

### 3.1 游戏状态、两条命令通道与暂停不变量

`BOOT → HOME/SELECT → READY → PLAYING → {PAUSED | READY | WON | LOST}`。`isSimulating()` 仅在 `READY` 或 `PLAYING` 且允许前台模拟时为真；`phase()` 返回状态枚举，供主循环判断每一次物理步后的转场。`PAUSED` 保存 `pausedFrom∈{READY,PLAYING}`。游戏 **状态机由 GameSession 管**；UI 的屏幕（Gameplay/Pause/Win/Lose 等）和 `ModalDialog` 另由 `AppController/UIController` 管，模态弹窗不属于模拟状态。

**控制通道 ControlCommand**（Pause、Resume、Retry、ExitToSelect、Confirm、Cancel、AppSuspend）在 `SDL_PollEvent` 之后、**每次显示循环的物理累积器之前**同步处理，即使没有任何 fixed tick 也会执行；所有转场输出新的 `SessionSnapshot.revision`。**玩法通道 GameplayCommand**（MovePaddle、Launch）只在 READY/PLAYING 的下一个固定步采样，并在 PAUSED/模态出现时丢弃未执行命令。两种命令不可混用一个“等 fixedTick 才消费”的队列。

- `Pause`：若 READY/PLAYING，立即保存 `pausedFrom`、切 PAUSED、清空累积器和玩法命令、取消触控捕获、暂停音频；本显示循环不再运行物理。
- `Resume`：仅前台、PAUSED、无模态时有效；立即恢复 `pausedFrom`，清空累积器和玩法命令/手指捕获、重置单调帧时间基准；从**下一次累积满 dt**才再次 fixedTick。无“先执行一轮物理才能恢复”的死锁。
- `Retry`：PAUSED 的确认框确认、WON/LOST 的重试按钮都可触发；在控制通道立即调用 `reset(currentLevel,config)`、恢复 READY/附着球、递增 revision、重新制作砖块全量渲染状态；不执行当前帧的物理补算。
- `ExitToSelect`：确认后退出至选择关卡，停止物理；系统 `AppSuspend` 立即 PAUSED（或保持终态）并禁止 Resume，直到回到前台且用户主动点“继续”。
- 暂停或重置**不能更改 `simTick`**，只更新 `revision`；WON/LOST 停止物理但允许控制命令导航。复位后新会话可将 `simTick` 从零计数（以 `sessionGeneration` 辅助区分）。


### 3.2 每个 fixed tick 的权威顺序

1. **采样玩法输入**：只读取控制通道已确认允许运行时留下的 `MovePaddle/Launch`；Pause/Resume/Retry 早已由主循环的控制通道处理，绝不在此等待。
2. **更新挡板**：直接按照已映射的世界位置 clamp 到 `[width/2, 24-width/2]`；准备球随挡板水平移动。
3. **活动球运动**：使用 tick 开始时按 BallId 升序的快照逐球进行 CCD，每个有效砖块命中立即扣 HP，并更新 `remainingTargets/score`；产生 `BrickDestroyed` 记录。已归零砖块对后续球立即表现为空格。
4. **本 tick 的新掉落道具入队**：B 砖刚摧毁产生道具；**从下一物理步开始下落**，避免刚生成就跨过碰撞区。
5. **更新既有掉落道具**：沿 y 轴正方向移动，检测与挡板矩形相交或离场；采集 `ItemCollected` 事件。
6. **消费已拾取道具**：按道具 ID 升序、每次增 3 球；新球位置与方向固定，**从下一物理步开始运动**。上限不足时每少 1 球补 50 分并提示。
7. **统一终局判定（高优先级在前）**：`remainingTargets==0 → WON`；否则若当前无活动球（不含待生成球）且状态仍为 `PLAYING`，生命减 1，并进入 `READY` 或 `LOST`。即使道具还在空中也不延迟全失球判定。
8. **提交事件与快照**：把本步砖块变化、UI 提示、音频聚合事件交给只读渲染/界面；不在渲染时再次改变玩法。

**同一步 B 砖击破恰为最后目标**：直接赢，未收集的道具不再影响结果。**同一步最后一球掉落又接到增球**：先消费道具，存在新球则不扣生命。**同一步最后目标击破且最后一球掉落**：赢优先。

### 3.3 主循环：每个 fixed tick 后重新检查状态（V1.3.1）

**核心不变量**：一次显示帧可追赶多个固定物理步，但**每一步之后**必须检查 `phase()` / `sessionGeneration`；一旦转入 `WON`、`LOST`、`PAUSED`，或者发生 `PLAYING→READY` 失球复位、`READY→PLAYING` 发球等状态转场，**立即终止本轮追赶并清空 `accumulator`**。不能仅在进入 `while` 之前检查 `isSimulating()`。本规则防止同一显示帧执行终态后的多余 fixedTick、误消耗玩法输入，以及 READY 状态被旧时间推进。进入终态后只有控制通道可触发新会话或导航。

```cpp
// 设计级伪代码：app.dispatchControlCommands() 将每个控制结果
// 当场交给 FrameCollector.onControlTransition(session, result)，并返回
// 本显示帧是否发生需要重置时钟的 Pause/Resume/Retry/退出/前后台转场。
while (app.running()) {
    const auto events = platform.pollEvents();
    ui.dispatchTopmostFirst(events);  // 系统 > 模态 > 导航/暂停 > 世界手势
    const ControlDispatchResult control = app.dispatchControlCommands();
    const double now = monotonicSeconds();

    if (control.resetTimebase || !app.isForeground() || !session.isSimulating()) {
        accumulator = 0.0;
    } else {
        accumulator += std::max(0.0, now - lastClock);
    }
    lastClock = now;

    // 同帧控制转场（包括 Resume）不使用旧时钟推进物理；下一显示帧重新累积。
    if (!control.resetTimebase && app.isForeground() && session.isSimulating()) {
        while (accumulator >= fixedDt && app.isForeground() && session.isSimulating()) {
            const GamePhase before = session.phase();
            const uint64_t generationBefore = session.sessionGeneration();
            const auto gameplay = input.consumeForTick();
            session.fixedTick(fixedDt, gameplay);
            frameCollector.copyTickOutputs(session);  // 先复制本 tick 事件及状态
            accumulator -= fixedDt;

            const bool transitioned = session.phase() != before ||
                session.sessionGeneration() != generationBefore;
            if (transitioned || !session.isSimulating()) {
                accumulator = 0.0;                 // 清掉旧阶段剩余追赶时间
                frameCollector.onSimulationTransition(session); // 保留已收集事件
                break;                             // 终态/失球/发球均不继续追赶
            }
        }
    }
    const float alpha = session.isSimulating()
        ? std::clamp(float(accumulator / fixedDt), 0.0f, 0.999999f) : 0.0f;
    FramePacket frame = frameCollector.finishFrame(session, alpha);
    ui.consume(frame.currentTick.hud, frame.events); // HUD 不存在第二份路径
    audio.consume(frame.audio);
    renderer.draw(frame);
}
```

- `ControlDispatchResult.resetTimebase` 对 Pause、Resume、Retry、退出、AppSuspend/恢复置真；它独立于 `GameSession.applyControl()` 的 `ControlResult`，由 AppController 汇总每帧处理结果。即使 0 fixed tick 也会执行控制通道。
- `FrameCollector.onSimulationTransition()` 只重设用于插值的前后快照、强制当前状态展示；**不得清空已经复制的 `LevelWon/LevelLost/LifeLost` 等本 tick 事件**。`finishFrame()` 一次性交给 UI/音频。
- `PLAYING→READY`（最后球丢失但仍有生命）与 `READY→PLAYING`（发球）同样切断本轮追赶，保证新阶段在下一显示帧以新时钟启动。
- 追赶过载时不能以跳过必要碰撞代替模拟；记录诊断并安全暂停。固定步时间保持 `1/120s`，不得随显示 FPS 改变。

### 3.4 渲染快照、控制事件与显示帧消费

每次真正执行 `fixedTick(n)` 后立即：①深拷贝本 tick `BrickChange`；②把 `GameEvent` 连同 `(sessionGeneration,simTick,sequence)` 复制到收集器自有队列；③复制完整 `RenderSnapshot(n)`（球、挡板、道具、HUD），不得跨 tick 保存 `span` 或模拟容器指针。**所有帧渲染 UI 只能访问 `frame.currentTick.hud`。**

`FrameCollector` 保存最近两个**相邻物理步**的快照 `RenderSnapshot(n-1)` / `RenderSnapshot(n)`，不是两个显示帧快照。`alpha = accumulator/fixedDt`，处于 0..1；只在同一会话且无状态转场时插值。仅当前出现的球/道具直接画当前位置；已删除实体不画。挡板 `centerX` 插值，外观采用当前状态。

- **零物理步并非一定零事件**：仅 0 tick 且无控制转场的显示帧，其新产生的物理事件为空；但 `Retry` 等控制可以产生 `SessionReset`。控制处理后，AppController 立即把 `ControlResult.events` 深拷贝给 `FrameCollector.onControlTransition()`，并同步更新当前 HUD 快照。没有 fixed tick 也应在本显示帧交付该事件、全量砖纹理和新状态，之后 drain 且不重放。
- `Retry` / 切关卡导致 `sessionGeneration` 改变时，先移除待显示队列中**属于旧会话**的瞬态事件，再加入新会话的 `SessionReset`，将两个渲染快照都设为新会话的当前值；不允许跨会话插值。由物理 tick 自身进入 WON/LOST 时**保留该终态 tick 的事件**，只禁止位置插值。
- 一个显示帧包含多个 tick 时，`BrickChange` 按最新砖状态合并，`FramePacket.fullBrickRgba` 有变更时复制完整 **61,440 字节**。CPU 端不需要逐 tick 回放纹理，GPU 最多一次整图上传；无砖变化和无重建请求时留空。
- 所有事件按 `sessionGeneration,tick,sequence` 排序；UI 使用全部离散事件一次性更新反馈，音频仅对高频 `BrickHit` 采样限流。不得因特效预算删掉权威计分、关卡进度或存档更新。
- 渲染/UI/音频只读取本次 `FramePacket`；消费完成后清空待交付事件。暂停 60 个 0 tick 显示帧不重复播放旧声效。GL 上下文重建要求 `FrameCollector.requestFullBrickUpload()`，立即从 CPU 当前砖状态提供全量数据，旧 GPU 句柄不得继续使用。


## 4. 微型砖块候选查询

对球在剩余时间 `h` 内的移动，`p1=p0+v*h`。用扫掠矩形：

\[
A = [\min(p_{0x},p_{1x})-r,\max(p_{0x},p_{1x})+r]\times[\min(p_{0y},p_{1y})-r,\max(p_{0y},p_{1y})+r]
\]

将 `A` 的连续坐标转换为 `floor(x/0.25)` 并 clamp 到网格范围，**只遍历覆盖格里的非空砖/墙**。若相同格会由不同扫描路径重复访问，按 CellIndex 去重。V1 使用扫掠 AABB 即可，不引入复杂空间树或 DDA 优化；若真机有明显候选格过多再替换 DDA。

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

**起点已重叠：** 若接触容差范围内，沿最小分离向量推出；球心在矩形内部时取最近面，四面同距离按固定优先顺序 `上→左→右→下`；不得按随机方向弹出。过深重叠要写诊断并恢复到该球上一有效位置。

### 5.2 最早碰撞与并列组

1. 从所有候选接触中取最小 `tMin`。
2. 把 `|t-tMin|<=timeEpsilon` 的接触组成一组，按 `kindPriority, cellIndex` 稳定排序（边界/固定墙优先于可破坏砖；挡板优先于砖）。
3. 组内可破坏砖**每格最多损伤一次**；按 cellIndex 升序处理命中和计分；墙永不扣 HP。
4. 若是挡板接触且球向下运动，**使用专用挡板出射**，不执行普通镜面反射；其余接触把相向法线相加后归一化得到 `n`，若因相互抵消长度接近零，选择 `-v·n` 最大的法线，完全并列按上述排序选第一条。
5. 标准反射 `v' = v - 2(v·n)n`，最后标准化到 `ball.speed`；沿法线移动 `separationEpsilon` 防止零时长重复接触。
6. 从剩余 `h-tMin` 继续找下一个接触，最多 24 次；超限时将球停留在当前安全位置，输出诊断、跳过此球当前步的剩余极短时间，下一步继续恢复，不准穿过墙体。持续 3 个物理步超限时，恢复到上一无重叠位置、使用向上安全速度并记错误计数。

同一步允许同一球在**离开后重新接触**同一砖（例如高频腔体反弹）；在一个接触组内不重复。新球只在下一步加入模拟，保证新增球不会改变当前球遍历期间的容器。

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
- 上限补偿：活动池容量剩余 `c`，新增 `min(c,3)`，未能新增的 `3-min(c,3)` 颗各补 `50` 分，UI 显示实际数量与积分；多次道具按稳定 ItemId 顺序应用。
- 计分只在砖块从 HP>0 变为 0 时一次性结算；按原始砖种 `1=100, 2=200, 3=300, B=100`；中途扣 HP 不另得分。
- 星级只根据通关时剩余生命：1→1星、2→2星、3→3星；失败不授星。最佳分与最佳星独立取最大值（可能来自不同局），这是有意定义。

## 7. C++ 模块接口（签名级契约，V1.3.1）

**本节是唯一公共事件与帧数据字段定义**。`03_TECHNICAL_ARCHITECTURE.md`、`10_UI_UX_DESIGN.md`、`14_VISUAL_DESIGN_AND_FEEDBACK.md` 不得定义不同名称的重复类型；HUD 使用 `FramePacket.currentTick.hud`，事件统一使用 `ItemCollected`（不再使用旧称 `BonusCollected`）。

```cpp
using BallId = uint32_t;
using ItemId = uint32_t;
using CellIndex = uint32_t;
enum class GamePhase { READY, PLAYING, PAUSED, WON, LOST }; // 其余菜单由 AppController 管
struct ControlCommand {
    enum class Type { Pause, Resume, Retry, ExitToSelect, Confirm, Cancel, AppSuspend };
    Type type;
};
// Confirm/Cancel 仅由 AppController 模态层消费并转换成 Retry/Exit 等；
// GameSession.applyControl() 不接收其模态命令本身。
struct GameplayCommand {
    enum class Type { MovePaddle, Launch };
    Type type; float mappedWorldX;
};
struct BallRenderState { BallId id; Vec2 position; float radius; uint8_t style; bool attached; };
struct PaddleRenderState { float centerX, centerY, width, height; uint8_t style; };
struct ItemRenderState { ItemId id; Vec2 position; float width, height; uint8_t kind; };
struct SessionSnapshot {
    uint64_t sessionGeneration, revision, simTick;
    uint32_t levelNumber; int lives, score, activeBalls, remainingTargets;
    bool awaitingLaunch;
};
struct RenderSnapshot { // 所有成员独立拥有数据
    SessionSnapshot hud;
    PaddleRenderState paddle;
    std::vector<BallRenderState> balls;
    std::vector<ItemRenderState> items;
};
struct BrickChange { CellIndex cell; uint8_t originalType; uint8_t newHp; };
struct GameEvent {
    enum class Type {
        BrickHit, BrickDestroyed, PaddleHit, ItemSpawned, ItemCollected,
        BallsSpawned, BallLost, LifeLost, LevelWon, LevelLost, SessionReset
    } type;
    uint32_t subjectId; int32_t value;
};
struct TickOutput { std::vector<BrickChange> changes; std::vector<GameEvent> events; };
struct ControlResult {
    bool stateChanged=false, levelReset=false, fullBrickUpload=false;
    std::vector<GameEvent> events; // Retry 可产生 SessionReset（无需 fixedTick）
};
struct ControlDispatchResult { bool resetTimebase=false; }; // AppController 的本帧汇总
struct OrderedEvent { uint64_t generation, tick; uint32_t sequence; GameEvent payload; };
struct AudioSummary { int brickHitCount; std::vector<OrderedEvent> priorityEvents; };
struct FramePacket {
    RenderSnapshot previousTick, currentTick; // HUD: frame.currentTick.hud
    std::vector<OrderedEvent> events;         // 本显示帧一次性交付
    AudioSummary audio;
    std::vector<uint8_t> fullBrickRgba;      // 空=无变化；非空=61440字节
    float alpha=0;
    bool interpolate=false;
};
class GameSession {
public:
    GamePhase phase() const;
    uint64_t sessionGeneration() const;
    bool isSimulating() const;
    void reset(const LevelDefinition&, const GameConfig&);
    ControlResult applyControl(ControlCommand); // 允许没有 fixedTick
    void fixedTick(float dt, std::span<const GameplayCommand>);
    SessionSnapshot snapshot() const;
    RenderSnapshot copyRenderSnapshot() const;
    TickOutput copyTickOutput() const;   // 本 tick 后立即深拷贝
    void writeFullBrickRgba(std::span<uint8_t> out61440) const;
};
class FrameCollector {
public:
    void copyTickOutputs(const GameSession&);
    void onSimulationTransition(const GameSession&); // tick 转场；保留本 tick 事件
    void onControlTransition(const GameSession&, const ControlResult&); // 采纳控制事件
    void requestFullBrickUpload(); // GL 上下文恢复时调用
    FramePacket finishFrame(const GameSession&, float alpha);
};
class Renderer { public: void draw(const FramePacket&); void onContextRecreated(); };
```

### 7.1 事件清单、产生条件及载荷（唯一命名）

| 事件 | 产生条件 | `subjectId` | `value` |
|---|---|---|---|
| `BrickHit` | 砖 HP 有效减少一次（包括本次归零） | `CellIndex` | 新 HP；归零为 0 |
| `BrickDestroyed` | HP 首次降为 0 | `CellIndex` | 本次增加的分数 |
| `PaddleHit` | 球由上方有效撞击挡板并反射 | `BallId` | 0；同一接触组仅一次 |
| `ItemSpawned` | B 砖销毁并产生掉落牌 | `ItemId` | 3（可获得球数） |
| `ItemCollected` | 挡板拾取掉落牌（旧称 BonusCollected 禁止使用） | `ItemId` | 3（请求新增球数） |
| `BallsSpawned` | 拾取已实际生成新球 | `ItemId` | 实际生成数 0..3 |
| `BallLost` | 单颗球从底边离屏、回收 | `BallId` | 0 |
| `LifeLost` | 本次生命最后一球丢失且无新球补充 | 0 | 扣命后剩余生命 |
| `LevelWon` | 最后目标砖摧毁，终态胜利 | 0 | 按剩余生命获得的星数 |
| `LevelLost` | 生命耗尽且未赢 | 0 | 0 |
| `SessionReset` | 控制通道确认重试/装载新会话 | 0 | 0 |

- `GameEvent::Type` **只有上述 11 个成员**。`ItemCollected` 在单一事件名称下承担拾取；不得新增同义名 `BonusCollected`。`PaddleHit` 是纯反馈事件，不允许根据 UI 动效再次改变物理方向。
- `BrickHit` 在打击后 HP=0 时仍会发生；视觉仅对 `value>0` 使用“受损高亮”，`BrickDestroyed` 专门处理归零破碎。`BallsSpawned.value` 是实际创建的球数，容量不足的补分由权威 `score` 体现在 HUD，不伪造三球全部生成。
- `OrderedEvent` 的代际、tick、顺序号来自唯一递增排序器；控制事件在 0 tick 情况下仍带当前 `sessionGeneration/simTick` 与唯一 `sequence`。同一事件交给一显示帧后不得重复交付。
- `AppController` 负责输入命令仲裁，`GameSession` 唯一写玩法数据；`FrameCollector` 收集独立值副本，`Renderer/UILayer/AudioMixer` 均不持有 `GameSession` 的可变引用。上层调用统一为 `ui.consume(frame.currentTick.hud, frame.events)`，禁止 `frame.hud` 或另设 `HudSnapshot` 重复来源。


## 8. GPU 合约与低复杂度实现

- 网格逻辑只有 `96×160`，RGBA8UI 整数纹理仅 `96×160×4=61,440 bytes`。**V1.3.1 优先选用“本帧有砖变化则更新整张 60KiB 状态纹理”，一帧最多一次 `glTexSubImage2D`**；比逐格／逐行大量 GL 调用更稳定也更简单。无变化不上传。将来有测量证据再改区域更新，**不预先实现脏矩形调度器**。
- 纹理内部格式选 `GL_RGBA8UI`，上传格式 `GL_RGBA_INTEGER/GL_UNSIGNED_BYTE`，着色器以 `usampler2D` + `texelFetch` 读取整数通道 `[type, hp, palette, flags]`；只允许最近邻采样，不使用插值，坐标与碰撞网格一一对应。
- 实例球体通过 1 次 `glBufferSubData`（或同等级批量写入）上传活跃球实例，按一次或少量批次绘制；**不逐球 Draw Call**。球视觉半径与物理半径一致，额外尾迹独立处理，不参加碰撞。
- Android GLES 3.0，Windows GL 3.3 Core；`#version 300 es` 和 `#version 330 core` 两个 shader 头；业务渲染路径保持一致。
- 上下文丢失时销毁 GPU 句柄并从 CPU `BrickField` 全量恢复。UI 对齐可视区域，而非重设世界/关卡坐标。
- 声音按显示帧最多合并播放 4 个击砖音效，并优先播放增球、通关/失球。音效丢弃不影响计分与砖块破坏事件。

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
| `remainingTargets ≥ 0` | 砖状态 HP 正变零时只减一次 |
| 所有活动球位置速度为有限数 | 非有限输入或求解输出：记录错误并恢复最近稳定状态 |
| 坐标与目标配置一致 | 导出/加载两端校验；资源版本不符拒绝加载 |
| 玩法事件在同一 tick 顺序稳定 | 球 ID + CellIndex + ItemId 三重稳定顺序 |
| Renderer 不修改砖或球 | 状态唯一路径：GameSession/Simulation |
| READY 必有且只有一颗附着球 | 全失球扣生命后重建，不带入上一生命的道具 |
| 不创建球球碰撞事件 | V1 无球球碰撞，球可互相穿越 |

## 11. 必须随实现提交的算法测试（不另设研究项目）

| 用例 | 关键输入 | 必须输出 |
|---|---|---|
| ALG-01 | 正向打到 1HP 砖 | HP=0，目标-1，计分一次 |
| ALG-02 | 同一个接触组碰到两个砖角 | 两砖各扣一次，法线确定 |
| ALG-03 | 高速越过厚度 0.25 的砖 | 不穿砖，命中最早接触 |
| ALG-04 | 球从角外掠过、未达到圆角半径 | 不误判撞角 |
| ALG-05 | 同步命中墙和砖 | 按法线/砖序规则稳定，墙 HP 不变 |
| ALG-06 | 一 tick 内多次撞墙 | 时间被正确消费，无无限反射 |
| ALG-07 | 两球同 tick 命中仅剩 1HP 砖 | 砖只销毁一次，积分只加一次 |
| ALG-08 | B 砖销毁且拾取 | 同步生成道具，拾取后下一 tick 生效 3 球 |
| ALG-09 | 1023/1024 球时拾取 +3 | 只能加 1/0 球，分别补 100/150 分 |
| ALG-10 | 最后一球丢失且拾取 +3 | 先加球，不扣命 |
| ALG-11 | 最后一目标销毁且所有球丢失 | 赢优先，星级按剩余命数 |
| ALG-12 | 失焦/暂停后恢复 | 无后台物理补帧；球不跳跃 |
| ALG-13 | 读取损坏或不兼容关卡 | 可定位错误，安全返回菜单 |
| ALG-14 | 任意 N 个 B 都未拾取 | 多球不凭空出现，失球规则准确 |

测试重点是算法**行为与可复现性**，不是要求每一个边角场景都做性能调研。实现 T06 与 T09 时完成对应单元测试，T15 再做实际关卡试玩。

## 12. V1.3.1 控制、渲染与优先级回归用例

| 测试 ID | 场景 | 必须结果 |
|---|---|---|
| CTRL-01 | 进入 PAUSED，连续显示 20 帧且无 fixedTick，点 Resume | **立即**切回原 READY/PLAYING，下一轮按新时间基准累积，不出现控制死锁 |
| CTRL-02 | PAUSED 中点击 Retry，确认模态出现，再选择确认 | 不执行物理即可重建关卡、进入 READY，生命/砖格重置，`revision` 更新 |
| CTRL-03 | 后台暂停 15 秒，回前台点 Resume | 没有 15 秒的追赶 tick，不跳球；前台未 Resume 时仍冻结 |
| CTRL-04 | 原有拖动中触发确认模态，之后抬手 | 模态吃掉事件，不发生 `Launch` / 挡板继续拖动 |
| CTRL-05 | 模态打开时点其下方 HUD 暂停按钮 | 模态优先，底层按钮不触发；Back 仅取消模态 |
| FRAME-01 | 同一显示帧运行 3 个 fixedTick，每次砖受损 | GPU 当前纹理为最后 HP，最多一次整图上传，UI事件按 tick 升序逐条一次消费 |
| FRAME-02 | 球在两个连续物理 tick 间移动，显示帧 0 tick | 仍使用相邻物理 tick 快照插值，不用上次显示帧的位置 |
| FRAME-03 | 某 tick 增 3 球、移除 1 球和出现掉落物 | 新球／新道具画当前位，消失球不画；挡板位置可正确插值 |
| FRAME-04 | 进入暂停后连续重绘 60 次 | 无重复砖击声、无重复 `ItemCollected`，球、板、道具不变化 |
| FRAME-05 | GL 上下文恢复或 Retry 后第一帧 | GPU 全量刷新砖图，上一关的球/道具不出现、不插值跨场景 |

对应实现任务 **T04/T07/T10**，测试随模块开发提交；这里是设计用例，尚未执行 C++ 测试。


## 13. V1.3.1 主循环终态与公共接口回归用例

| ID | 输入条件 | 预期与明确边界 | 任务 |
|---|---|---|---|
| `LOOP-01` | 累积器含 5 个 dt，第 2 tick 击破最后目标进入 `WON` | **只调用 2 次 fixedTick**；第 2 步的 `LevelWon` 事件交付一次；余时归零；下一显示帧 0 物理步 | T04/T06/T08 |
| `LOOP-02` | 累积器含 5 个 dt，第 2 tick 失去最后一命进入 `LOST` | **只调用 2 次 fixedTick**；`LifeLost/LevelLost` 各交付一次，无后续动作；余时归零 | T04/T06/T08 |
| `LOOP-03` | 累积器含 5 个 dt，第 2 tick 最后一球离屏且仍有生命，`PLAYING→READY` | 停在第 2 tick，READY 附着球快照正确，剩余追赶时间归零；不能用同帧旧输入再发球 | T04/T06 |
| `LOOP-04` | READY 接收到 Launch 的当前步后进入 PLAYING | 该步执行一次并立即结束追赶；下个显示帧才继续累积新阶段物理时间 | T04 |
| `FRAME-06` | PAUSED 中控制通道 Retry，显示帧 0 fixed tick | `frame.currentTick.hud` 为重置后状态；events 恰有新代际 `SessionReset`，全量砖纹理已提供；下一帧不重复 | T04/T07 |
| `API-01` | 按 §7 定义 C++ 头文件并编译 UI/音频订阅方 | 编译期可访问 `frame.currentTick.hud`，**不存在** `frame.hud`；11 个枚举成员准确一致 | T07/T10 |
| `API-02` | 完成真实挡板反射、拾取 +3、场景重试 | 分别按载荷定义产生 `PaddleHit`、`ItemCollected`、`BallsSpawned`、`SessionReset`，旧名 `BonusCollected` 不存在 | T06/T09/T10 |

**注意**：这些是必须随对应 C++ 代码提交并执行的测试规格；当前 V1.3.1 不含可执行 C++ 引擎，不能把设计用例计为已通过。
