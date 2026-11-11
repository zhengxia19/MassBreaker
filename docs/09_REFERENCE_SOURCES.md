# 技术资料与设计来源

**日期** 2026-11-11｜供开发中核对 API、构建方式和技术结论。

## 官方技术资料

1. SDL3 Android 工程及生命周期：<https://wiki.libsdl.org/SDL3/README-android>
2. SDL3 CMake 项目引入：<https://wiki.libsdl.org/SDL3/README-cmake>
3. SDL3 官方发布存档（3.4.20 于 2026-11-03 列出）：<https://www.libsdl.org/release/>
4. SDL3 OpenGL ES profile：<https://wiki.libsdl.org/SDL3/SDL_GLProfile>
5. SDL3 GL context 创建：<https://wiki.libsdl.org/SDL3/SDL_GL_CreateContext>
6. SDL3_ttf 源码与发布：<https://github.com/libsdl-org/SDL_ttf/releases>
7. SDL3_mixer 3.2.4 源码与发布：<https://github.com/libsdl-org/SDL_mixer/releases>
8. Android NDK/CMake 官方文档：<https://developer.android.com/ndk/guides/cmake>
9. Android Gradle native build：<https://developer.android.com/studio/projects/gradle-external-native-builds.html>
10. Tiled 编辑器与导出：<https://www.mapeditor.org/>、<https://doc.mapeditor.org/en/stable/reference/json-map-format/>；Tiled JSON 层字段 `offsetx/offsety` 明确为像素偏移，`x/y` 为 tile 单位偏移，本项目运行时 schema 不支持这些位移，导出必须拒绝。

## 手机性能与功耗资料

- [Android 功耗优化](https://developer.android.com/games/optimize/power)：目标帧率与显示刷新率、热状态和功耗策略。
- [Android Frame Pacing](https://developer.android.com/games/sdk/frame-pacing)：OpenGL/Vulkan 呈现节奏与提交队列问题。
- [Android Power Profiler](https://developer.android.com/studio/profile/power-profiler)：ODPM 设备支持及整机测量边界。
- 仓库固定版本 SDL3 的 `include/SDL3/SDL_events.h`、`SDL_video.h`：阻塞事件等待与 swap interval API；实际跨平台行为须在 T02/T07 验证。

## 游戏参考素材

用户提供的三段 MP4（参考素材未放进交付文档包）：

- X status `2119996452865007780`：黄色高密度砖阵与中央通道。
- X status `2119996305334534265`：棕红色砖阵与分叉隔板。
- X status `2119996364327440609`：紫色砖阵与双腔体结构。

这些视频用于分析游戏表现与空间组织，不把画面未明确证明的道具规则、源码结构或实际弹球数量描述为原作事实。产品规则以本项目自定义文档为准。

## 需要开发时核对但无需预研的事项

- 固定版 SDL3、SDL_ttf、SDL_mixer 在实际 Android NDK/Gradle 组合中的编译配置。
- Google Play 上架时的 target SDK、64 位、签名和隐私申报要求。
- 选定字体、音效、图像的版权和打包授权。

以上是正常工程配置/发行检查，不是技术选型尚未决定。
