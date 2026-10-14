# 运行

## 一、三种跑法

| 方式 | 命令 | 说明 |
| --- | --- | --- |
| **① 双击（唯一日常方式）** | `启动语音悬浮球.bat` | 内容只有一行：`start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0voice_ball.py"` —— **`pythonw.exe` 意味着没有控制台窗口** |
| ② 命令行版 | `venv\Scripts\python voice_agent.py` | 无界面，同样是热键触发。**⚠️ 它 `print()`，所以要配 `python.exe`（有控制台）才有输出** |
| ③ 开发 | `venv\Scripts\python voice_ball.py` | 与 ① 相同，但用 `python.exe`（**有控制台，能看到日志**） |

**首次运行**：README 说"会下载 Whisper 模型（约 1.5 GB）"——
**但本机的模型已经在了**（`models\` 下两个，共 3,152 MB），所以不会下载。

> ⚠️ **`voice_ball.py` 用的是本地模型目录**：`resolve_model_path(cfg)` 按 `config.json` 的
> `whisper_model` 拼出 `models\faster-whisper-<值>\`，**不是 HF 缓存**；
> **目录不存在时打 WARNING 并回退 `faster-whisper-medium`**。
> 所以 `HF_ENDPOINT=hf-mirror.com` 那两行**只有在模型缺失时才会用到**。

**当前两个模型**（2026-10-09 实测）：

| 目录 | 大小 | 说明 |
| --- | --- | --- |
| `models\faster-whisper-medium\` | 4 文件 / **1,459.7 MB** | 兜底档位 |
| `models\faster-whisper-large-v3-turbo\` | `model.bin` **1,542.9 MB** | **当前在用**（含 `.cache\` 共 1,546.5 MB） |

## 二、`config.json` —— 五个字段

`D:\MyProject\voice_tool\config.json`（**163 B**，2026-10-09 实测内容）：

```json
{
  "whisper_model": "large-v3-turbo",
  "hotkey": "<ctrl>+<alt>+<space>",
  "ball_pos": [1041, 8],
  "mic_device": null,
  "language": "zh"
}
```

| 字段 | 是什么 |
| --- | --- |
| `whisper_model` | 模型档位（本机是 `large-v3-turbo`）—— ✅ **生效**：决定读 `models\faster-whisper-<值>\` |
| `hotkey` | 全局热键（pynput 语法） |
| **`ball_pos`** | 🔴 **悬浮球在屏幕上的位置** —— **这是用户拖动后存下来的** |
| `mic_device` | 指定麦克风设备（`null` = 自动选） |
| 🆕 `language` | 转写语言（`zh`）；写 `"auto"` 让模型自判 |

> ✅ **2026-10-09 更正**：旧版本这里写着 "`whisper_model` 对悬浮球【毫无影响】，是死字段"。
> **已经修好了** —— 新增 `resolve_model_path(cfg)`，配置真的决定用哪个模型目录。
> 详见 [README.md](README.md) 第 7.2 节。

> ⚠️ **两个入口各有一份 `load_config()`，默认值不同**：
> `voice_ball.py` 默认 `medium`，`voice_agent.py` 默认 `small`。
> **它们读的是同一个 `config.json`**，所以只在文件缺失时才有差别。

> ⚠️ **`voice_ball.py` 读 config 用的是 `utf-8-sig`**（能容忍 BOM），
> `voice_agent.py` 用 `utf-8`。**手工编辑过这个文件的话，前者更宽容。**

## 三、热键

**默认 `<ctrl>+<alt>+<space>`** —— 切换录音（开始/停止）。

`voice_agent.py` 里还有一个容错：**如果 `config.json` 里写的是 `ctrl+alt+space`（不带尖括号），
它会自动补成 `<ctrl>+<alt>+<space>`。**

## 四、日志

`logs\voice_ball.log`（**当前活动日志**）+ `logs\voice_ball.log.1`（**2 MB，已轮转**）。

**用了 `logging.handlers` 的轮转**。

> 🔴 **⚠️ 一个操作上的坑**：**应用运行时，`logs\voice_ball.log` 被进程占着** ——
> **`Get-FileHash` 读不了它**（报 "being used by another process"）。
> **备份它要用 `robocopy`**（能读）。**核验它只能靠大小，不能靠哈希。**
> （整理时实测踩到过。）

**代码里有一处专门的教训**（`voice_ball.py` L1547）：

> 以前这里只 `print()`，而 **`pythonw` 下 stdout 是丢弃的，失败完全无声**

**→ 所以这个项目改成写日志了。** 这是个值得学的做法。

## 五、🔴 开机自启：怎么开关

**代码里有三个函数**（`voice_ball.py` L1551-1579）：

| 函数 | 作用 |
| --- | --- |
| `_autostart_command()` | 拼出 `"<BASE_DIR>\venv\Scripts\pythonw.exe" "<BASE_DIR>\voice_ball.py"` |
| `is_autostart_enabled()` | 读 `HKCU\...\Run\VoiceBall` 是否存在 |
| `set_autostart(enable)` | 写 / 删那个值 |

**注册表位置**：
```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  名称: VoiceBall
  值  : "D:\MyProject\voice_tool\venv\Scripts\pythonw.exe" "D:\MyProject\voice_tool\voice_ball.py"
```

**关掉自启的两种方式：**

```powershell
# 方式一：手动删那个值
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'VoiceBall'
```

**方式二**：如果应用界面里有"开机自启"的开关，点掉它（会调 `set_autostart(False)`）。

**打开**：`set_autostart(True)`，或手工写回那个值。

> ### 🔴 搬动项目之后必须做的一件事
>
> **注册表里那个值是绝对路径。搬了项目，它就不对了 —— 而且失效是静默的**
> （开机什么都不发生，不报错）。
>
> **自愈**：在新位置跑一次程序 → 重新 `set_autostart(True)`（或手工改那个值）。

## 六、已知限制

| # | 限制 | 说明 |
| --- | --- | --- |
| 1 | **仅 Windows** | `winreg`、PyAudio 的 MME/WASAPI、`pythonw.exe` |
| 2 | **需要 NVIDIA GPU** | `device="cuda"` 是首选 |
| 3 | **但代码里已经有 CPU 回退了** | 🔴 见下 |
| 4 | **需要 NVIDIA 驱动与 CUDA 运行库** | `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` 已列在 `requirements.txt` |
| 5 | **5.15 GB 录音无自动清理** | 🔴 见 [data.md](data.md) —— 每天约 **172 MB**，一年约 **63 GB** |
| 6 | **模型在项目内、未链接到 `_shared`** | 🔴 见 [deps.md](deps.md) 第四节（本机两个模型 3.08 GB） |

### ⚠️ 第 3 条 —— **`README.md` 里有一句话已经过期**

**仓库根的 `README.md` 写着**：

> **需要 NVIDIA GPU** —— 转写固定走 CUDA + float16；**没有 GPU 需要在代码里改成 CPU**

**但代码里已经有回退了**（`voice_ball.py` L810-814）：

```python
try:
    self.model = WhisperModel(MODEL_DIR, device="cuda", compute_type="float16")
    self.device = "cuda"
except Exception:
    log.warning("CUDA 加载失败，回退 CPU", exc_info=True)
    try:
        self.model = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8")
        self.device = "cpu"
```

**→ 没有 GPU 时它会自动退回 CPU，不需要改代码。**

> **⚠️ 本次整理没有改那句话** —— 那是仓库根 `README.md` 的内容，
> **改了就是改动**（而且它是 GitHub 门面）。**在这里记下正确的事实即可。**

（`voice_agent.py` 则是**硬走 CUDA，没有回退** —— 两个入口在这点上不一致。）

---

## 七、🔴 两个入口的差异表

> **2026-10-03 补充段新增。** 此前文档只说「另有命令行版 `voice_agent.py`，逻辑更轻」——
> **没有把两边到底差在哪列出来。实测有 12 处差异。**

| # | 项 | **`voice_ball.py`**（主程序） | **`voice_agent.py`**（命令行版） | 出处 |
| --- | --- | --- | --- | --- |
| **1** | **行数 / 大小** | **1,485 行 / 76,173 B** | **141 行 / 4,844 B**（**主程序的约 1/10**） | —— |
| **2** | **GUI** | ✅ **PySide6 悬浮球** + 托盘 + 拖拽 + Toast + 波浪动画 | 🔴 **无** —— 只有 `print()`（`:78` `:90` `:116`） | `:1084` vs —— |
| **3** | 🔴 **路径基准** | ✅ **`__file__` 绝对**（`:50-56`）—— **在哪启动都对** | 🔴 **CWD 相对**（`:35` `config.json` · `:67` `audio_temp` · `:68` `transcripts`）—— **只能在项目根启动** | `:50-56` vs `:35,67,68` |
| **4** | **默认模型档位** | `medium`（`:135`） | `small`（`:39`） | 同 |
| **5** | ✅ **`config.json` 的 `whisper_model` 字段** | ✅ **2026-10-09 起生效** —— `resolve_model_path(cfg)` 拼出 `models\faster-whisper-<值>\`，不存在则回退 medium（**旧版是死字段**） | ✅ **也生效** —— 直接当模型名传给 `WhisperModel` | 同 |
| **6** | 🔴 **CPU 回退** | ✅ **有**（`:810-814`，cuda/float16 失败 → cpu/int8） | 🔴 **没有** —— `:79` 直接 `device="cuda"`，**无 try** | 同 |
| **7** | 🔴 **麦克风通路自检** | ✅ **约 500 行**（`:164-664`）—— 枚举 / 优先级 / 死路判据 / 自动回退 | 🔴 **无** —— `:94` 直接 `pa.open(...)`，**不指定设备、不探测** | 同 |
| **8** | **单实例** | ✅ 命名管道 `VoiceBall_SingleInstance`（`:1588`） | 🔴 **无** | —— |
| **9** | **开机自启** | ✅ `winreg` 写 `HKCU\...\Run\VoiceBall`（`:1566-1579`） | 🔴 **无** | —— |
| **10** | **日志** | ✅ `RotatingFileHandler`（2 MB × 3）+ `sys.excepthook` + `threading.excepthook`（`:61-90`） | 🔴 **只有 `print()`** —— **`pythonw` 下会全丢** | 同 |
| **11** | **`mic_device` / `ball_pos` 字段** | ✅ 两个都认（`:489` `:1315` `:1110` `:1444`） | 🔴 **两个都不认** | —— |
| **12** | **尾音收集 / 闲置卸载** | ✅ `TAIL_S=0.6`（`:119`）· `IDLE_UNLOAD_S=300`（`:120`） | 🔴 **都没有** | —— |

### 7.1 汇总

| | `voice_ball.py` | `voice_agent.py` |
| --- | --- | --- |
| **共同点** | 热键切换录音 · 录音存 wav · faster-whisper 转写 · **写剪贴板** · **转写存 txt** | 同 |
| **它独有** | GUI / 通路自检 / 单实例 / 自启 / 日志 / 尾音 / 闲置卸载 / CPU 回退 / `__file__` 基准 / **热键看门狗** / **按需加载** | —— |
| ~~**它独有**~~ | ~~——~~ | ~~✅ `whisper_model` 字段真的生效~~ **← 2026-10-09 起主程序也生效了，这条不再成立** |
| 🔴 **谁在调它** | **`启动语音悬浮球.bat`**（唯一日常入口）· **`Workbench\config\tools.json`** | 🔴 **没有任何东西调用它**（实测：`.bat` 只调 `voice_ball.py`） |

> 🔴 **判定：详见 [README.md](README.md) 第九节与 `log.md`。**
> **本轮【判不了】它是"现役第二入口"还是"弃用的早期版本"** —— 见
> `project_manager\docs\log.md` 的"未解决"。
