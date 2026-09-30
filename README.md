<div align="center">

# 语音悬浮球

**点一下开始录音，再点一下停止 —— 本地转写，结果直接进剪贴板。**

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/Qt-41CD52?style=flat-square&logo=qt&logoColor=white)
![CUDA](https://img.shields.io/badge/CUDA-76B900?style=flat-square&logo=nvidia&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D4?style=flat-square&logo=windows11&logoColor=white)

![License](https://img.shields.io/badge/license-MIT-4B5563?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/3431481073/voice_tool?style=flat-square&color=4B5563)
![Repo Size](https://img.shields.io/github/repo-size/3431481073/voice_tool?style=flat-square&color=4B5563)
![Status](https://img.shields.io/badge/status-active-4B5563?style=flat-square)

</div>

---

## 这个项目解决什么问题

想随手记一句话的时候，代价其实很高：手要离开正在做的事，打开笔记，起个文件，想个标题。

这个悬浮球把整件事压成两下点击 —— 点一下开始说，再点一下，文字已经在剪贴板里了，直接粘到任何地方。

转写完全在**本机**跑（faster-whisper + GPU），音频不离开这台电脑。

## 快速开始

```bash
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python voice_ball.py
```

首次运行会下载 Whisper 模型（约 1.5 GB），之后离线可用。
双击 `启动语音悬浮球.bat` 也可以 —— 它调用 `venv\Scripts\pythonw.exe`，没有控制台窗口。

## 功能

| 功能 | 说明 |
| --- | --- |
| 悬浮球点击录音 | 点一下开始、再点一下停止并转写；录音时球体有实时波浪反馈 |
| 全局热键 | 默认 `<ctrl>+<alt>+<space>` 切换录音，可在 `config.json` 改 |
| 本地转写 | faster-whisper（medium）跑在本机 GPU 上，音频不出机器 |
| 自动复制 | 转写完成立刻写入剪贴板 |
| 转写存档 | 每次结果按时间戳存进 `transcripts/` |
| 闲置卸载模型 | 转写结束 5 分钟后自动释放模型，归还约 1.9 GB 显存 |
| 麦克风通路自检 | 逐条探测 MME / DirectSound / WASAPI，识别「整条返回数字静音」的死路并自动回退 |
| 单实例 | 重复启动不会再开一个球 |
| 拖拽与托盘 | 球体可拖到任意位置，右键菜单退出 |

另有一个命令行版本 `voice_agent.py`：无界面，同样是热键触发，逻辑更轻。

## 已知限制

- **仅 Windows** —— 依赖 `winreg`、PyAudio 的 MME/WASAPI 通路与 `pythonw.exe`
- **需要 NVIDIA GPU** —— 转写固定走 CUDA + float16；没有 GPU 需要在代码里改成 CPU
- **仓库不含模型与录音** —— `models/`、`audio_temp/`、`transcripts/` 都在 `.gitignore` 里；
  克隆后首次运行会自行下载模型、自行创建这两个数据目录
- 需要可用的 NVIDIA 驱动与 CUDA 运行库（`nvidia-cublas-cu12` / `nvidia-cudnn-cu12` 已列在 `requirements.txt`）

## 许可证

MIT

本项目采用 MIT 许可证，详见 LICENSE。
