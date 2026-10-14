# OUTPUT-SLOT —— 我往外给

> 按 `D:\MyProject\CLAUDE.md` **§8.4 的固定格式**写。
> 🔴 **程序只读下面「固定标题 + 那张两列表」这一块**；`## 详情` 自由写，**程序一个字节都不读**。
>
> **标题与列名一个字不许换**：`## 我往外给` / `锚点` / `是什么`。

## 我往外给

| 锚点 | 是什么 |
| --- | --- |
| D:\MyProject\voice_tool\transcripts | 转写文本存档目录（一条一次，UTF-8 纯文本） |
| D:\MyProject\voice_tool\audio_temp | 原始录音目录（16-bit PCM 单声道 wav） |
| D:\MyProject\voice_tool\logs | 运行日志目录（轮转 2MB × 3） |
| D:\MyProject\voice_tool\config.json | 本地配置（5 个字段） |
| D:\MyProject\voice_tool\services.yaml | 服务声明（`services: []`） |
| D:\MyProject\voice_tool\models | 本地 Whisper 模型目录（两份第三方权重副本，**非本项目产出**） |

## 详情

> 下面这些**程序不读**，只给人看。字段表 / 怎么取 / 假设 / 失效模式都在这里。

---

### 1 · 🔴 剪贴板 —— 唯一出工程的交付（**没有锚点**）

**系统剪贴板没有文件路径，也不是端口，所以它进不了上面那张表。** 但它是本项目**唯一离开工程**的交付，必须写在这里。

| 项 | 内容 |
| --- | --- |
| **产出物** | 最近一次转写的**纯文本**（每次转写覆盖写入，**不是追加**） |
| **放在哪** | **系统剪贴板** —— **没有文件路径**，由 Windows 持有 |
| **格式** | 纯文本（`str`）。**无编码声明、无换行约定、无结构、无版本号** |
| **怎么取** | 任何程序调用系统剪贴板 API 读取：<br>· Windows：`Get-Clipboard`（PowerShell）<br>· Python：`pyperclip.paste()`<br>· 人：`Ctrl+V` |
| **假设** | 🔴 **无任何假设可依赖** —— 见下面三件事 |

#### ⚠️ 必须先说清的三件事

1. **无声明** —— 没有任何地方约定"剪贴板里是什么"。别的程序被动读取时，**无法区分它是不是本项目写的**。
2. **随时被覆盖** —— 用户自己的任何一次复制、**任何别的程序写剪贴板，都会覆盖它**。它的存活期取决于"下一个人什么时候复制"。
3. **不可追溯** —— 没有时间戳、没有来源标记。**离开这个项目之后就没有任何痕迹。**

> 🔴 **它承载了这个工具存在的全部理由**（根 `README`：「文字已经在剪贴板里了，直接粘到任何地方」），
> **却没有任何一处文档能约束它** —— 因为它是系统级共享资源，本项目对它**没有所有权**。
>
> **已列进 `project_manager\docs\SLOT-CASCADE.md` 第八节「待议：系统级槽」（状态：待议，不拍板）。**

---

### 2 · 转写存档 —— `D:\MyProject\voice_tool\transcripts`

| 项 | 内容 |
| --- | --- |
| **产出物** | 每次转写的文本，**一条一次写入，之后不再改动** |
| **放在哪** | `D:\MyProject\voice_tool\transcripts\{YYYYMMDD_HHMMSS}.txt`<br>**无子目录**。实测 2026-10-09：**4,367 个文件 / 1.81 MB** |
| **格式** | **UTF-8 纯文本，内容就是转写结果本身** —— **没有表头、没有时间戳字段、没有元数据**。文件名里的 `YYYYMMDD_HHMMSS` **是唯一的时间信息** |
| **怎么取** | 直接按文件名读 |
| **假设** | ① 文件名是本地时间 `YYYYMMDD_HHMMSS`（15 字符）<br>② **wav 与 txt 不是一一对应** —— 转写结果为空时**不写 txt**（见下面细节） |

#### 格式细节

| 项 | 值 |
| --- | --- |
| 编码 | UTF-8 **无 BOM**（`open(..., "w", encoding="utf-8")`） |
| 行数 | **1 行**（转写结果拼成一行；换行符取决于模型输出，本工程不加工） |
| 标点 | **取决于模型档位** —— `medium` 基本不带标点；`large-v3-turbo`（当前）自带逗号/句号 |
| 平均体积 | 约 414 B/条（实测 1,808,059 B ÷ 4,367） |
| 🔴 **不是每段 wav 都有对应 txt** | **转写结果为空时不写文件**。实测 wav 4,413 vs txt 4,367，**差 46 个** |

> 🔴 **不可再生** —— 这是**用户每天说的话的文本版**。删了没有副本。

---

### 3 · 原始录音 —— `D:\MyProject\voice_tool\audio_temp`

| 项 | 内容 |
| --- | --- |
| **产出物** | 录音的原始 wav（**用户的声音**） |
| **放在哪** | `D:\MyProject\voice_tool\audio_temp\{YYYYMMDD_HHMMSS}.wav`<br>**无子目录**。实测 2026-10-09：**4,413 个文件 / 5,270 MB（5.15 GB）** |
| **格式** | RIFF/WAV。**16-bit PCM** · **单声道** · **采样率 = 采集通路实际采样率**（见下） |
| **怎么取** | 任何 wav 解码器（`wave` / `soundfile` / ffmpeg）。<br>🔴 **时长请从文件头读采样率，不要假设 16000** |
| **假设** | ① 文件名与同刻的 `transcripts\{同名}.txt` **尽量对应**（但不保证，见第 2 项）<br>② 目录**只增不减**（没有任何自动清理） |

#### 格式细节（🔴 不要假设固定采样率）

| 项 | 值 |
| --- | --- |
| 位深 / 通道 | `sampwidth = 2`（16-bit）· `nchannels = 1`（单声道） |
| **采样率** | **取自实际生效的采集通路**（`path.rate`）。<br>本机平时走 **MME / 16000**；若回退到 WASAPI 则可能是 **48000** |
| **首尾静音** | 🔴 **写入前已裁掉首尾的数字静音**（`trim_edge_silence`）—— 所以文件里的**第一个样本就是有声内容**，不存在开头的零填充 |
| 命名 | `YYYYMMDD_HHMMSS.wav` |
| 时间跨度 | 2026-08-31 13:35:21 → 2026-10-09 17:35:37（实测） |
| 🔴 **无自动清理** | **没有任何 `os.remove` 作用于这个目录**。实测增速约 **172 MB/天**，一年约 **63 GB** —— 见 [data.md](data.md) |

> **删它会丢"声音"，不丢"信息"** —— 文本版在第 2 项里。
> **但那是用户的声音，决定权在他。** 见 [data.md](data.md) 第三节的三个选项。

---

### 4 · 运行日志 —— `D:\MyProject\voice_tool\logs`

| 项 | 内容 |
| --- | --- |
| **产出物** | 运行行为记录（通路选择、每次录音的实测指标、异常 traceback） |
| **放在哪** | `D:\MyProject\voice_tool\logs\voice_ball.log` + 轮转档 `voice_ball.log.1` … `.3`<br>实测 2026-10-09：**2 个文件 / 3.09 MB** |
| **格式** | 文本，`logging` 默认行格式：`%(asctime)s [%(levelname)s] %(threadName)s %(message)s` |
| **怎么取** | 直接读文本。**⚠️ 应用运行时活动文件被进程占用** —— `Get-FileHash` 读不了，备份要用 `robocopy` |
| **假设** | ① 行格式是上面那个模板（人排错可以依赖，**程序别依赖**）<br>② ✅ **可清** —— 纯诊断信息，删了不影响功能 |

#### 格式细节

| 项 | 值 |
| --- | --- |
| 轮转 | `RotatingFileHandler`，**2 MB × 3 份** |
| 级别 | 开 `DEBUG` 也记（探测细节走 DEBUG） |
| 关掉它 | **改代码**（`setup_logging()`）—— **没有配置开关** |

---

### 5 · 本地配置 —— `D:\MyProject\voice_tool\config.json`

| 项 | 内容 |
| --- | --- |
| **产出物** | 本程序自己的行为参数（`ball_pos` 会**被程序自己写回**） |
| **放在哪** | `D:\MyProject\voice_tool\config.json`，实测 **163 B** |
| **格式** | JSON，UTF-8 **无 BOM**，`indent=2`。**5 个字段**（表见下） |
| **怎么取** | 直接 `json.load`。**能容忍 BOM**（读取用 `utf-8-sig`） |
| **假设** | ① **读取只发生在启动时** —— 运行中改文件**不会热重载**<br>② 字段名拼错 = **静默按默认值走** |

| 字段 | 类型 | 实测值 | 改它会怎样 |
| --- | --- | --- | --- |
| `whisper_model` | string | `"large-v3-turbo"` | ✅ **生效** —— 决定读 `models\faster-whisper-<值>\`（目录不存在则回退 medium） |
| `hotkey` | string | `"<ctrl>+<alt>+<space>"` | ✅ 生效 —— pynput 语法 |
| `ball_pos` | [int,int] | `[1041, 8]` | ✅ 生效 —— 悬浮球位置，**程序退出时自己写回** |
| `mic_device` | object\|null | `null` | ✅ 生效 —— 手动指定麦克风；`null` = 自动探测 |
| `language` | string | `"zh"` | ✅ 生效 —— 转写语言；写 `"auto"` 让模型自判 |

> ⚠️ **`voice_agent.py`（命令行版）读同一份文件，但只认 `whisper_model` 和 `hotkey`**，
> 且它的默认值是 `small`（主程序是 `medium`）。差异表见 [run.md](run.md) 第七节。

---

### 6 · 服务声明 —— `D:\MyProject\voice_tool\services.yaml`

| 项 | 内容 |
| --- | --- |
| **产出物** | 服务声明，内容是 `services: []`（**本项目无常驻服务**） |
| **放在哪** | `D:\MyProject\voice_tool\services.yaml`，实测 **1,776 B** |
| **格式** | YAML |
| **怎么取** | 直接读；由 `service-manager` 消费 |
| **假设** | 没有端口、没有常驻服务 —— 见 [service.md](service.md) |

---

### 7 · 本地模型目录 —— `D:\MyProject\voice_tool\models`（**不是本项目产出**）

| 项 | 内容 |
| --- | --- |
| **产出物** | **没有产出** —— 这是两份**第三方权重的本地副本** |
| **放在哪** | `D:\MyProject\voice_tool\models\faster-whisper-medium\`（1,459.7 MB）<br>`D:\MyProject\voice_tool\models\faster-whisper-large-v3-turbo\`（1,542.9 MB）<br>共 **3,152 MB / 17 文件**（含 turbo 的 `.cache\`） |
| **格式** | CTranslate2 模型目录：`model.bin` + `tokenizer.json` + `vocabulary.*` + `config.json` |
| **怎么取** | 当普通目录读（`WhisperModel(dir, ...)`） |
| **假设** | 目录名必须是 `faster-whisper-<config 里的值>`；缺 `model.bin` 会加载失败 |

> 🔴 **为什么把它列进「我往外给」**：**它是我"存下来的、别人可能读的"东西**，
> 而它**恰恰是重复副本问题的现场**（本机 medium 至少还有 `video-workbench` 和 `D:\models\` 两份）。
> **列出来，别人才不会再去下一份。**
>
> 🔴 **但它不该长在这里** —— 按 `CLAUDE.md` §2.1，通用大文件应放 `_shared\models\` **一份正本、链接共用**。
> **本项目的正确来源应是那里，不是这个目录。** 现状见 [deps.md](deps.md) 第四节。

---

### 附 · 触发入口（**不属于输出槽，待迁到 `TRIGGER-SLOT.md`**）

> §8 要求槽分三份，**控制流归 `TRIGGER-SLOT.md`**。**本项目该文件尚未建立**，
> 先把信息暂存在这里，免得丢。

| 入口 | 说明 |
| --- | --- |
| `启动语音悬浮球.bat`（双击） | 唯一日常入口 |
| `D:\MyProject\Workbench\config\tools.json` →「工具箱」→「语音转文字」 | 被 `Workbench` 用绝对路径启动 |
| `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\VoiceBall` | **开机自启**（登录时由 Windows 执行） |
| 全局热键 / 点悬浮球 | 人机交互 |

---

## 一句话

> **上面那张表是我的池子清单（6 个锚点）。**
> **最深的一条不在这张表里：剪贴板 —— 它没有锚点，却承载了这个工具存在的全部理由。**
> **最重的一条占了 5.15 GB，且没有任何自动清理。**
