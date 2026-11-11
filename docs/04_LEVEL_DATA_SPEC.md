# 关卡格式、编辑规范与校验工具（V1.3.1）

**编号：** MB-DATA-004｜**状态：** Schema V1 冻结；资源和导出／验证脚本已同步更新

## 1. 唯一数据流

**Tiled `.tmj`（可编辑唯一源） → Python 导出器 → `assets/levels/Lxxx.json`（游戏运行唯一输入） → `BrickField`。** `design/levels/Lxxx.png` 是从同一个运行时 JSON 生成的设计预览图，不是碰撞数据。禁止手工修改 JSON 后不回写 Tiled。

地图 `96×160` 正交有限图，Tiled tile 为 `8×8` 编辑像素，映射到 `24×40` 世界，单格 0.25。**地图顶层 `width/height` 与砖层自身 `bricks.width/height` 必须分别都是严格整数 `96/160`。即使砖层扁平 `data` 长度仍为 15,360，也不得接受 48×320、160×96 等错误的砖层尺寸。****源地图所有顶层图层（含 bricks、markers、decor）必须满足 `offsetx=offsety=0`、`x=y=0`、`parallaxx=parallaxy=1`（缺省取这些值）；V1 禁止 group 层与组合变换。出现任何非零偏移时导出器必须直接报错，不允许静默丢弃。**物理原点左上、x 向右、y 向下。Tiled `bricks` Tile Layer 为必需，`markers` Object Layer 为必需（恰有一个 point `ball_spawn` 与一个 point `paddle`）；`decor` 为可选且不参与碰撞。

## 2. 字符与唯一物理语义

| GID¹ | 运行时字符 | HP | 目标 | 行为 |
|---:|:---:|---:|:---:|---|
| 0 | `.` | 0 | 否 | 空 |
| 1 | `1` | 1 | 是 | 普通砖 |
| 2 | `2` | 2 | 是 | 加固砖 |
| 3 | `3` | 3 | 是 | 强化砖 |
| 4 | `#` | — | 否 | 不可破坏墙 |
| 5 | `B` | 1 | 是 | 击破产生可拾取 `+3` 道具 |

¹ 表中 1–5 为当前 tileset `firstgid=1` 的 GID。导出器按 firstgid 计算 local tile，禁止对任意 GID 直接硬编码为字符；不支持 Flip GID（遇到明确报错）。

## 3. 运行时 JSON Schema V1（完整实例）

参见 [`examples/level_l001.json`](../examples/level_l001.json)。每个资源均包含：

```json
{
  "schemaVersion": 1,
  "id": "L001", "title": "Central Entry", "chapter": 1, "theme": "amber",
  "world": {"width": 24, "height": 40},
  "grid": {"origin": [0, 0], "cellSize": 0.25, "columns": 96,
           "rows": ["<长度为96的行字符串，实际文件共有160行>"]},
  "spawn": {"ball": [12, 37.65], "paddle": [12, 38.0]}
}
```

**注意：上述 JSON 中的 `rows` 是字段说明占位符，不是可运行关卡；实际示例引用 `examples/level_l001.json`。** 其中 `grid.rows` 必须正好 160 行，每行 96 个 `.`/`1`/`2`/`3`/`#`/`B` 字符；完整文件通常约 17KB，不含实时 HP 或球位置。`chapter` 要满足 `chapter = floor((levelNum-1)/5)+1`。

游戏规则配置为独立的 [`assets/config/gameplay.json`](../assets/config/gameplay.json)，包括球速、半径、生命、挡板、增球与分数。**单关不得自定义另一套碰撞参数**。

## 4. 关卡几何与异常规范

- 静态砖/墙仅允许行 `0..113`；`114..159` 是挡板控制区，不得出现砖或墙。
- 出生点 `(12,37.65)` 附着在挡板 `(12,38.0)` 上方，校验其物理占位、格位和世界边界。
- 所有 `B` 至少有一个四邻空白格；L001–L004 不放 B、L005 开始出现。
- 加载失败、版本/ID/字符非法：报告关卡文件名与错误行列，返回安全菜单/错误页，**不能进入半初始化物理世界**。
- 固定墙与球半径的基本通路检测：使用 0.125 世界单位取样网格，只把固定墙当作永久阻挡；可破坏砖假定未来能清除，检测目标是否存在理论接触位置。**这是保守结构筛查，不证明弹球可按某种实际反射角度打穿或真实通关。**
- 关卡完全获胜、实际时长、B 道具拾取率属于引擎实现后的人工试玩验收，不假装由地图工具完成。

## 5. 现有工具与命令（无 Docker）

```bash
# 将 Tiled 编辑源转换为运行时关卡
python tools/level-export/export.py --input levels-src/L001.tmj --output assets/levels/L001.json

# 严格检查30关资源，并逐文件确认与源地图一致
python tools/level-export/validate.py --dir assets/levels --source levels-src

# 检查静态墙造成的明显结构隔断（非通关证明）
python tools/level-export/geometry.py --dir assets/levels

# 更新每关目标砖、墙、道具、耐久等统计清单
python tools/level-export/build_manifest.py --dir assets/levels --out design/levels/manifest.json

# 从运行时 JSON 同步生成预览（仅设计工具需 Pillow）
python tools/level-export/render.py --dir assets/levels --out design/levels
```

所有 `export/validate/geometry/build_manifest` 仅用 Python 标准库；`render.py` 使用 Pillow，仅在开发机安装，不打包进 Android。导出失败必须非零退出，禁止 `assert` 作为唯一校验。`manifest.json` 从实际资源重新统计，不手写会过期的数量。

## 6. 文件改动与内容版本

- 修改关卡必须先改 `levels-src/Lxxx.tmj`，再更新运行时 JSON、manifest 和对应 PNG；`examples/level_l001.json` 应与正式 L001 完全一致。
- 资源统一通过源控制记录；通过 `validate.py --source` 执行一致性回归。额外执行 `python -m unittest discover -s tools/level-export -p "test_*.py" -v`，检查 `bricks/markers` 的 `offsetx/offsety=8`、`bricks` 异常尺寸（等长 data 仍需报错）及其他非法变换均报错（`LevelError`、CLI 非零退出）。新增砖种/修改坐标语义需提升 schemaVersion，并同步更新导出器、C++ 加载器和单测。
- 发版前 `assets/levels/` 和 `assets/config/` 应为 APK 的只读资源，客户端不得写回；进度写入应用私有目录。
- 设计团队可用 Tiled 实际编辑；本包仅验证 JSON/数据转换，**没有声称在 Tiled GUI 内逐个操作了30张地图**。

## 7. Tiled 图层偏移问题的固定处理原则

Tiled 图层的 `offsetx` / `offsety` 是**像素偏移**，不是注释；标记层偏移会影响球/挡板位置，砖块层偏移会改变视觉与碰撞网格的对应关系。当前运行时 JSON 的坐标结构**没有表达图层平移的字段**，因此 V1.3 选择更简单且安全的方案：

1. 导出器读取所有顶层图层，执行 `validate_layer_transform()`；非零 `offsetx/offsety`、`x/y` 或非默认 parallax 即明确报出图层名、字段和值；`group` 层直接拒绝。
2. **先完整校验源图，再写输出 JSON**；错误导出命令非零退出，原有正式资源不被覆盖。
3. 恢复为所有变换为零后重新导出；`.tmj → JSON → 预览` 一致性由 `validate.py --source` 保障。
4. 任何未来需要支持非零偏移的需求必须新立 schema 变更并同步 JSON 坐标转换、物理加载器与预览工具，不能偷偷忽略字段。

回归文件：[`tools/level-export/test_export.py`](../tools/level-export/test_export.py)。

## 8. V1.3.1 砖层尺寸缺陷修正（编辑关卡前立即生效）

- `export.py` 在读取 `bricks.data` 前，分别读取 `bricks.width` / `bricks.height`，要求两者的 Python 类型都是 `int`（不接受 `bool`、字符串、浮点数），且严格等于 `96/160`。
- 图层尺寸与顶层地图尺寸分别检查；`len(data)==15360` 只是独立的附加条件，绝不替代尺寸检查。错误示例：`48×320`、`160×96`、`96×159`，即使实际 data 个数正确仍须报错。
- 当前 CLI 在 `convert()` 成功完成全部检查后才打开输出文件写入，异常时返回非零状态且不覆盖旧 JSON；`test_export.py` 增加该行为的回归测试。
- 现有 30 关尺寸正常，**不需要重新设计关卡**；以后修改任何 `.tmj` 先执行工具回归。
