# 打包为 Windows exe

dterrain 用 PyInstaller 打包为单文件 exe。**PyInstaller 不能跨平台交叉编译**，exe 必须在 Windows 环境生成。

## 方式一：在 Windows 机器上手动打包

1. 安装 Python 3.9+（勾选 "Add to PATH"）。
2. 下载 ffmpeg 静态二进制（Windows 版）：
   - https://www.gyan.dev/ffmpeg/builds/ （选 release-essentials）
   - 解压后把其中的 ffmpeg.exe、ffprobe.exe 复制到本项目根目录的 bin\ 目录。
3. 在项目根目录运行：
   ```bat
   scripts\build.bat
   ```
4. 产物在 dist\dterrain.exe，双击或在命令行直接运行。

## 方式二：GitHub Actions 自动打包（无需本地 Windows）

1. 把本项目推到 GitHub 仓库。
2. 在仓库 Actions 页面手动触发 build-exe 工作流。
3. 完成后在 Artifacts 下载 dterrain-windows 压缩包，内含 dterrain.exe。

## 常见打包坑

- PyInstaller 会联网检测依赖；若失败可加 --clean 重试。
- 打包后 exe 体积约数十 MB（含 Python 运行时 + ffmpeg），属正常。
- 若运行时提示找不到 ffmpeg，检查 bin\ffmpeg.exe 是否随包打入（--add-data 的 "bin" 目标路径需与代码里 sys._MEIPASS/bin 查找逻辑一致）。
- 本机 macOS 上无需打包，直接 python3 -m dterrain ... 即可联调。
