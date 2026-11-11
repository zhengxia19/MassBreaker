# 关卡格式、编辑规范与校验工具

**编号：** MB-DATA-004｜**状态：** Schema V1 冻结；资源和导出／验证脚本已同步更新

## 1. 唯一数据流

**Tiled `.tmj`（可编辑唯一源） → Python 导出器 → `assets/levels/Lxxx.json`（游戏运行唯一输入） → `BrickField`。** `design/levels/Lxxx.png` 是从同一个运行时 JSON 生成的设计预览图，不是碰撞数据。禁止手工修改 JSON 后不回写 Tiled。

地图 `96×160` 正交有限图，Tiled tile 为 `8×8` 编辑像素，映射到 `24×40` 世界，单格 0.25。**地图顶层 `width/height` 与砖层自身 `bricks.width/height` 必须分别都是严格整数 `96/160`。即使砖层扁平 `data` 长度仍为 15,360，也不得接受 48×320、160×96 等错误的砖层尺寸。**

**源地图所有顶层图层（含 bricks、markers、decor）必须满足 `offsetx=offsety=0`、`x=y=0`、`parallaxx=parallaxy=1`（缺省取这些值）；V1 禁止 group 层与组合变换。出现任何非零偏移时导出器必须直接报错，不允许静默丢弃。**物理原点左上、x 向右、y 向下。Tiled `bricks` Tile Layer 为必需，`markers` Object Layer 为必需（恰有一个 point `ball_spawn` 与一个 point `paddle`）；`decor` 为可选且不参与碰撞。

顶层 `tilewidth/tileheight` 也必须是严格整数 `8/8`。整数尺寸不接受浮点数、布尔值或字符串。`bricks.data` 必须为未压缩整数数组且长度为 15,360；长度检查不能代替砖层自身宽高检查。图层变换值须为有限数；缺省为零偏移和单位视差，不支持嵌套 group。

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

仅支持一个 tileset。`firstgid` 为正整数，`tilecount` 为不少于 5 的整数；GID 必须为非负整数且无 Flip 标志。只有全局 GID `0` 表示空格；非零 GID 必须满足 `firstgid <= gid < firstgid + tilecount`，再按 `local = gid-firstgid+1` 映射到 1–5。例如 `firstgid=2,gid=1` 必须报错；正确整体平移的 GID 应导出等价网格。

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

## 6. 资源维护与回归

- 修改关卡必须先改 `levels-src/Lxxx.tmj`，再更新运行时 JSON、manifest 和对应 PNG；`examples/level_l001.json` 应与正式 L001 完全一致。
- 资源统一通过源控制记录；通过 `validate.py --source` 执行一致性回归。额外执行 `python -m unittest discover -s tools/level-export -p "test_*.py" -v`，检查 `bricks/markers` 的 `offsetx/offsety=8`、`bricks` 异常尺寸（等长 data 仍需报错）及其他非法变换均报错（`LevelError`、CLI 非零退出）。新增砖种/修改坐标语义需提升 schemaVersion，并同步更新导出器、C++ 加载器和单测。
- 发版前 `assets/levels/` 和 `assets/config/` 应为 APK 的只读资源，客户端不得写回；进度写入应用私有目录。
- 设计团队可用 Tiled 实际编辑；当前项目仅验证 JSON/数据转换，**没有声称在 Tiled GUI 内逐个操作了30张地图**。
- 导出器先完成源图及运行时结构校验，再打开目标 JSON；非法偏移、尺寸、整数类型、firstgid 或 GID 必须报错并保留既有输出。运行时不支持图层平移，不能静默忽略 Tiled 变换。
- [test_export.py](../tools/level-export/test_export.py) 的 18 项测试覆盖：正常源图、零变换、非零 offset/x/y/parallax/group、砖层等长异常尺寸、顶层浮点/布尔尺寸、firstgid 与 GID 边界、正确 GID 平移、CLI 失败保留输出，以及 30 关源数据一致性。
