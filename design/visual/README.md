# 视觉规范图说明

- `../ui/final/03_gameplay.png` 从当前 `assets/levels/L003.json` 绘制微砖与墙；球、得分、生命仅为设计示意，不是物理模拟输出。
- `../ui/final/03_gameplay_multiball.png` 从 L028 真实地图绘制；+3 掉落物与小球位置为示意。
- `component_states.png` 为放大后的颜色和形状状态稿，**不是直接用于游戏的最终 sprite 贴图**。
- 所有 UI 原型图由 `tools/visual-preview/render_ui.py` 生成，使用本机已有字体绘制；字体二进制不在交付物中。运行时代码需依法接入有授权的字体。
- 屏幕中的 96×160 地图来自运行时 JSON，避免继续沿用 V1.1 的连续色块旧示意。
