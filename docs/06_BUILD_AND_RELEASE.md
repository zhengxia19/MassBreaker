# 构建、运行与 Android 发布规范

**编号** MB-BUILD-001｜**版本** 1.0｜**状态** 规划中的开发操作规程，非已完成构建记录

## 1. 版本基线与工具

| 工具 | 基线 |
|---|---|
| C++ | C++20 |
| SDL3 | **3.4.20**；固定第三方 Git tag/commit |
| SDL3_ttf | 3.2.2（接入 UI 字体阶段） |
| SDL3_mixer | 3.2.4（接入音频阶段；需要 SDL3 3.4+） |
| CMake | 使用与 NDK/构建环境兼容的固定版本 |
| Windows | Visual Studio 2022 C++ 工具链 / MSVC，或兼容 Clang |
| Android | Android SDK（基线 SDK 36）、NDK r28c 或更新兼容版，Gradle 模板固定版本 |
| 设备 | Android `arm64-v8a`；`minSdk 26` 为本项目选择 |
| 编辑器 | Tiled 1.12.2 |

**版本管理**：正式仓库建立时固定 AGP、Gradle wrapper、NDK、CMake、SDL3 三库版本；不要使用 `latest`、master 无提交号等浮动依赖。正式发布时 `targetSdk` 根据当时适用的 Google Play 要求锁定，不在设计文件中凭空预设未来商店政策。

## 2. 目录与目标

```text
MassBreaker/
├── CMakeLists.txt            # 统一顶层构建
├── CMakePresets.json         # Windows / Android 相关配置
├── core/                     # 与平台无关的 C++ 引擎及玩法
├── desktop/main.cpp          # Windows 启动入口
├── android/                  # SDL3 官方 Android 工程模板派生
├── third_party/{SDL,SDL_ttf,SDL_mixer}/
├── assets/{levels,shaders,audio,images,fonts}/
├── levels-src/               # Tiled 编辑源文件
├── tools/                    # 关卡转换、生成和检查
└── tests/
```

`massbreaker_core` 为通用 C++ 库目标。Windows 构建为 `MassBreaker` 可执行程序；Android 必须按 SDL3 官方 Android 说明将游戏启动目标构建成名为 **`main` 的共享库**，并让 Gradle 打包 SDL3 所需的 Java 适配层和原生库。不能将 Windows 的 exe 直接作为 Android 目标。

## 3. Windows 本地构建

前提：配置好 VS2022 C++、CMake、Git，固定版本依赖已放入 `third_party/` 或作为 Git 子模块检出。

开发仓库达到 T01 后，目标使用如下命令：

```powershell
cmake -S . -B build/windows -G "Visual Studio 17 2022" -A x64
cmake --build build/windows --config Debug
# 可执行文件预期在生成目录对应的 Debug 子目录
```

这些是本项目计划采用的命令形式，**目前交付仅包含设计文档，尚无可执行的 CMakeLists.txt**。工具链按项目第一次实编译结果将准确路径写入仓库 README。

开发中保留 Windows 桌面入口，以快速调整关卡、重现碰撞问题和观察 FPS。桌面入口使用 OpenGL 3.3 Core，Android 使用 OpenGL ES 3.0，两者共享业务规则及 GLSL 逻辑。

## 4. Android 工程集成

采用 [SDL3 官方 Android README](https://wiki.libsdl.org/SDL3/README-android) 指引的标准 Gradle 工程路线：

1. 从固定版本 SDL3 源码的 `android-project` 建立 `android/` 工程，保留必要 Java `SDLActivity` 适配层；应用自身逻辑不使用 Java。
2. Gradle 的 `externalNativeBuild` 指向根目录 CMake，配置 `arm64-v8a` 和所需 Android min/target SDK。
3. CMake 的 Android 分支生成 `add_library(main SHARED ...)`，链接 `massbreaker_core`、SDL3 和 GLES/EGL 等平台依赖。
4. Android app 的 assets 从根目录 `assets/` 打包；Debug、Release 使用同一份关卡资源。
5. 真机开启开发者选项及 USB 调试，`adb devices` 确认设备可用。
6. 在 `android/` 内执行（Windows 为 `gradlew.bat`）：

```powershell
cd android
.\gradlew.bat assembleDebug
.\gradlew.bat installDebug
adb logcat -s SDL:V MassBreaker:V
```

Debug 构建以后，正式版按项目签名配置执行 `assembleRelease` / `bundleRelease`；签名密钥、密码不得提交 Git。上面日志标签示例需要与项目实际实现一致，**不是现成可用的固定标签**。

## 5. 应用标识与版本

- 应用内部名称：`Mass Breaker`。
- `applicationId`：先使用临时的 `com.example.massbreaker`，**正式首次发布前必须替换为实际拥有的唯一包名**，一旦上架不得随意修改。
- 建议首个开发版本 `0.1.0`；正式版本从 `1.0.0` 起，`versionCode` 递增。
- 锁定竖屏；无网络权限；不申请外部存储访问权限。
- Release 必须开启合理编译优化并保留符号映射/符号包供崩溃分析；不开启未经验证的全局 `fast-math`，避免碰撞重现性变化。

## 6. 资源装载

- APK 内的关卡、图像、声音、Shaders 为只读 assets；用 SDL3 支持的 I/O API 读取，避免假设 Android APK 内文件等价于真实磁盘路径。
- 存档放应用内部可写目录，不放 assets。
- 运行时不需要加载 TMX 文件；Tiled 资源先由工具输出精简 JSON。
- 字体文件必须确认授权；正式打包可裁剪需要的中文字形子集，减小包体。**本项目文档不包含任何第三方字体文件。**

## 7. Android 发布前清单

- [ ] Android debug APK 可直接安装、游玩、暂停、恢复。
- [ ] Release 签名由开发者安全保存；签名、版本、应用名称、包名一致。
- [ ] Android AAB / APK 可构建，target API 满足发布时官方要求。
- [ ] 关卡资产、音效、字体、图标等有合法许可和清单。
- [ ] 30 关内容完整，首启无需网络，无未完成入口。
- [ ] 安装→升级→重新打开不丢已有进度。
- [ ] 应用截图、图标、简述、版本发布记录准备齐全。

## 8. 可信官方资料

- SDL3 Android：https://wiki.libsdl.org/SDL3/README-android
- SDL3 CMake：https://wiki.libsdl.org/SDL3/INTRO-cmake
- SDL3 官方发布：https://www.libsdl.org/release/
- SDL3_ttf：https://github.com/libsdl-org/SDL_ttf/releases
- SDL3_mixer：https://github.com/libsdl-org/SDL_mixer/releases
- Android NDK CMake：https://developer.android.com/ndk/guides/cmake
- Android native Gradle：https://developer.android.com/studio/projects/gradle-external-native-builds.html
- Tiled JSON：https://doc.mapeditor.org/en/stable/reference/json-map-format/
