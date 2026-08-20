# dterrain — 无人机航拍视频 → 坐标点位地形地貌识别

> **两种形态**：① 双击即用的**图形界面版** `dterrain.exe`（选视频/航线 → 填坐标 → 点按钮出结果）；② 命令行版 `dterrain-cli.exe`。二者共用同一套核心。

针对**消费级无人机（无内嵌 GPS / 无时间戳字幕）**的工具：给定航拍视频 + 航线坐标信息，对落在航线上的任意坐标点位，自动抽取对应视频帧，识别该点位的地形地貌类别。

云端识别采用 **DeepSeek**（本地提取图像特征 → 以文本交给 DeepSeek 语义判断）。

## 工作原理

\`\`\`
输入1: 航拍视频 (mp4/mov)          —— 消费级视频，无 GPS、无时间戳
输入2: 航线坐标 (CSV: lat,lon)     —— 自动航线图上的航点（坐标来自航线规划）
输入3: 目标坐标（单点 / 清单 / 沿线采样）

[1] 坐标匹配 -> 目标坐标 -> 最近航点(haversine) -> 按「匀速」映射到视频时间戳
[2] 抽帧     -> ffmpeg 按时间戳抽取 1 帧 JPEG
[3] 本地特征 -> numpy+Pillow 提取颜色/纹理特征（植被、水域、裸地、边缘密度…）
[4] 云端判断 -> 特征以文本发给 DeepSeek(deepseek-v4-flash/pro) -> 归一化到地貌类别
[5] 输出     -> 每点 {类别, 置信度, 帧截图, 依据} + results.json / results.csv
\`\`\`

> **为什么是「匀速」**：消费级视频没有 GPS，坐标只能来自「航线图」。工具假设无人机沿航线匀速飞行，把视频总时长按航点间距（累计距离）分摊到每个航点。请把视频剪辑到从航线起点起飞时开始；也可用 --start-offset 校正「起飞后 N 秒才到航线起点」。

> **为何「本地特征 + DeepSeek」**：DeepSeek 官方云端 API（api.deepseek.com）目前只提供文本模型 deepseek-v4-flash / deepseek-v4-pro，**不支持图片/视觉输入**。因此本工具在本地把图片算成一组统计特征（植被占比、水域占比、裸地占比、亮度、饱和度、边缘密度等），再把这些数字以文本发给 DeepSeek 做语义判断——既真正用到 DeepSeek，又无需视觉 API。

## 两种识别后端

| 后端 | 说明 | 适用 |
| --- | --- | --- |
| features（默认） | 本地特征 + DeepSeek 文本模型 | 你现在的场景，零视觉 API 成本 |
| vision | 直接把图片发给视觉大模型 | 将来 DeepSeek 支持视觉，或你有其它视觉模型时 |
| mock | 确定性假结果 | 无 Key 联调/跑通流程 |

## 安装（开发/联调）

\`\`\`bash
pip install -r requirements.txt   # requests + Pillow + numpy
# 需系统已装 ffmpeg / ffprobe（在 PATH 中）
\`\`\`

## 快速开始

\`\`\`bash
# 0) 生成演示数据（合成视频 + 航线 + 无时间戳航点）
python3 scripts/make_demo_data.py --out demo --seconds 30

# 1) 查看视频与轨迹信息（无 GPS，用航线航点文件）
python3 -m dterrain info --video demo/demo_video.mp4 --route demo/demo_waypoints.csv

# 2) 识别单个坐标（lon,lat）——先用 mock 跑通
python3 -m dterrain single --video demo/demo_video.mp4 --route demo/demo_waypoints.csv \
    --coord "116.000040,40.000100" --backend mock --out out

# 3) 批量识别坐标清单
python3 -m dterrain batch --video demo/demo_video.mp4 --route demo/demo_waypoints.csv \
    --coords demo/demo_points.csv --backend mock --out out

# 4) 沿线等间隔采样
python3 -m dterrain sample --video demo/demo_video.mp4 --route demo/demo_waypoints.csv \
    --every 5 --backend mock --out out
\`\`\`

## 接入 DeepSeek（真实识别）

配置 API Key 后去掉 --backend mock 即可（默认就是 DeepSeek features 后端）：

\`\`\`bash
# A) 命令行
python3 -m dterrain single --video a.mp4 --route 航线.csv --coord "116.1,40.0" \
    --api-base "https://api.deepseek.com" --model "deepseek-v4-flash" --api-key "sk-xxxx"

# B) 配置文件 ~/.dterrain/config.json
# {"api_base": "https://api.deepseek.com", "model": "deepseek-v4-flash", "api_key": "sk-xxxx"}

# C) 环境变量 DTERRAIN_API_KEY（配合配置文件中的 api_base/model）
\`\`\`

> DeepSeek API Key 在 platform.deepseek.com 获取；模型可选 deepseek-v4-flash（便宜快）或 deepseek-v4-pro（更强）。

## 子命令

| 命令 | 作用 |
| --- | --- |
| single | 识别单个坐标点位 |
| batch | 批量识别坐标清单（CSV：lon,lat[,id]） |
| sample | 沿航线等间隔采样（--every 秒 / --count 点数） |
| info | 查看视频与轨迹信息 |

## 航线坐标文件格式

无 GPS 时坐标来自「航线图」，支持三种：

- **CSV**（最常用）：\`lat,lon\` 两列即可（可加 alt/time 列）
- **GPX / KML**：标准航迹/航线文件

## 默认地貌分类（9 类，可 --categories 覆盖）

水域、农田、森林、草地、裸地/荒漠、建筑、道路、山地、其他

## 坐标约定

--coord 与坐标清单均采用「经度,纬度」（lon,lat），与 GPS/GeoJSON 一致。

## 打包 Windows exe（GitHub Actions 推荐）

PyInstaller 不能跨平台交叉编译，exe 须在 Windows 生成。两种方式：

1. **GitHub Actions（推荐，无需本地 Windows）**：把项目推到 GitHub → 在 Actions 页面手动触发 build-exe 工作流 → 从 Artifacts 下载 dterrain.exe。
2. **本地 Windows**：装 Python 3.9+，下载 ffmpeg 到 bin\，运行 scripts\build.bat。

详见 [build.md](build.md)。
