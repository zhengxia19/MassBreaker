# 视觉设计图说明

- 当前视觉依据为 [视觉规范](../../docs/14_VISUAL_DESIGN_AND_FEEDBACK.md)、[visual.json](../../assets/config/visual.json) 和 `design/ui/final/` 下的页面设计图。
- `../ui/final/03_gameplay.png` 使用 L003 当前 JSON 绘制微砖与墙；`../ui/final/03_gameplay_multiball.png` 使用 L028。球、道具、得分与生命为设计示意，不是模拟输出。
- `component_states.png` 是放大的颜色与形状规范图，不是可直接打包的 sprite。
- 图片由 `tools/visual-preview/render_ui.py` 读取关卡和视觉配置生成；设计机须安装 Pillow 并设置 `MB_UI_FONT`。字体二进制不在交付资源中，运行时字体及授权由 T12 落实。
