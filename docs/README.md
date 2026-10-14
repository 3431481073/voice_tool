# voice_tool（语音悬浮球）

**点一下开始录音，再点一下停止 —— 本地转写，结果直接进剪贴板。**

PySide6 桌面应用 + faster-whisper（**本机 GPU，音频不出机器**）。

> **整理状态**：2026-10-03 按 `project_manager/docs/PLAYBOOK.md` 整理。
> **代码零改动。数据一个都没搬。** 整理记录见 [log.md](log.md)。

---

## 一、它是什么

想随手记一句话的时候，代价其实很高：手要离开正在做的事，打开笔记，起个文件，想个标题。

**这个悬浮球把整件事压成两下点击** —— 点一下开始说，再点一下，文字已经在剪贴板里了。

**转写完全在本机跑**（faster-whisper **large-v3-turbo** + CUDA），**音频不离开这台电脑**。

**它每天在被重度使用**：2026-09-26 ~ 10-03 期间，每天 99~215 条转写。
**今天（10-03）已经写了 196 个文件。**

| 功能 | 说明 |
| --- | --- |
| 悬浮球点击录音 | 点一下开始、再点一下停止并转写；录音时球体有实时波浪反馈 |
| 全局热键 | 默认 `<ctrl>+<alt>+<space>`，可在 `config.json` 改 |
| 本地转写 | faster-whisper（**large-v3-turbo**，档位由 `config.json` 的 `whisper_model` 决定）跑在本机 GPU 上 |
| 自动复制 | 转写完成立刻写入剪贴板 |
| 转写存档 | 每次结果按时间戳存进 `transcripts\` |
| **按需加载 + 闲置卸载** | **启动不加载模型**；首次录音时与收音**并行**加载；转写结束 **5 分钟**后自动释放，归还约 **1.9 GB** 显存 |
| 麦克风通路自检 | 逐条探测 MME / DirectSound / WASAPI，识别"整条返回数字静音"的死路并自动回退 |
| 单实例 | 重复启动不会再开一个球 |
| 拖拽与托盘 | 球体可拖到任意位置，右键菜单退出 |
| **开机自启** | 🔴 写 **`HKCU\...\CurrentVersion\Run\VoiceBall`** —— 见第三节 |

**另有一个命令行版 `voice_agent.py`**（166 行，无界面，同样是热键触发，逻辑更轻）。

## 二、形态一览

| 项 | 值 |
| --- | --- |
| **形态** | **Windows 桌面应用**（PySide6 悬浮球），**有一个常驻进程** |
| **常驻服务** | **无** —— **不监听任何端口**。但有一个一直活着的 `pythonw.exe`（悬浮球本体），见 [service.md](service.md) |
| **端口** | **不占任何端口**（单实例用的是**命名管道** `VoiceBall_SingleInstance`，不是端口） |
| **开机自启** | 🔴 **有** —— `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\VoiceBall` |
| **平台** | **仅 Windows** —— `winreg`、PyAudio 的 MME/WASAPI、`pythonw.exe` |
| **硬件** | **需要 NVIDIA GPU**（`device="cuda"`）—— **但代码有 CPU 回退**，见 [run.md](run.md) |
| **版本控制** | ✅ git · **1 commit**（`ab32579`）· 🟠 **工作区有未提交改动**（2026-10-09 起：`voice_ball.py` / `config.json` + 本 `docs\` 三份新文档） |
| **规模** | **约 11.2 GB** —— **但纯源码只有 0.081 MB**（`voice_ball.py` 76,173 B + `voice_agent.py` 4,844 B）<br>2026-10-09 实测：`audio_temp` 5,270 MB · `models` 3,152 MB · `venv` 3,047 MB · `transcripts` 1.81 MB · `logs` 3.09 MB |

## 三、🔴 自启的绝对路径陷阱

`voice_ball.py` 的 L1515-1516：

```python
AUTOSTART_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "VoiceBall"
```

**实测注册表里的值（2026-10-03 只读查询）：**

```
VoiceBall = "D:\MyProject\voice_tool\venv\Scripts\pythonw.exe" "D:\MyProject\voice_tool\voice_ball.py"
```

**它是 `_autostart_command()` 拼出来的 —— 两个绝对路径。**

> ### 🔴 搬动这个项目 → 自启**静默失效**
>
> 开机时 Windows 会去执行那个路径 —— **路径不存在，就什么都不发生。**
> **不报错、不弹框、没有任何提示。** 用户只会觉得"今天怎么没看见球"。
>
> **自愈方式**：在新位置跑一次程序，然后重新 `set_autostart(True)`
> （或者手工改注册表里那个值）。
>
> **⚠️ 这比另一种失效模式更隐蔽** —— 对照 `markdown-reader`：
> 它的右键菜单失效是**响亮**的（点下去报"找不到文件"）。
> **而这一条，你根本不会知道它失效了。**

## 四、架构

```
voice_ball.py  (76,173 B / 1,485 行)   ← 主程序
├── setup_logging()            写 logs\voice_ball.log（轮转 2MB×3）+ 装 sys/threading excepthook
├── setup_cuda_path()          把 pip 装的 nvidia-* 的 bin 注入 PATH（ctranslate2 只认 PATH）
├── MicManager / MicPath       麦克风通路探测与回退（MME / DirectSound / WASAPI）
│   ├── _open_validated()      逐个"通道数 × 采样率"组合试，用实测电平判死路
│   ├── trim_edge_silence()    落盘前裁掉首尾数字静音（设备启动期有 ~400ms 零填充）
│   └── resolve_model_path()   模型目录 ← config 的 whisper_model；不存在则回退 medium
├── DECODE_ARGS / _transcribe_kwargs()
│                              vad_filter + 关 condition_on_previous_text + temperature=0
├── Controller                 状态机：idle → recording → transcribing → idle
│   ├── ensure_model_loading() 按需加载：与录音【并行】，把加载时间藏进用户说话里
│   ├── _load_model()          WhisperModel(path, cuda, float16) → 失败回退 cpu/int8
│   └── _schedule_idle_unload() IDLE_UNLOAD_S = 300 秒后释放模型（还 ~1.9 GB 显存）
├── FloatingBall(QWidget)      悬浮球本体（拖拽、波浪、右键菜单）
├── Toast(QWidget)             提示
├── SingleInstanceServer       QLocalServer，命名管道 "VoiceBall_SingleInstance"
├── _hotkey_watchdog()         每 0.3s 把 pynput 卡住的按键状态与物理状态对账
└── set_autostart()            HKCU Run 注册表
```

**所有数据目录都用 `__file__` 相对定位**（这是本工程里路径写得最健康的一个项目）：

```python
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR      = os.path.join(BASE_DIR, "models", "faster-whisper-medium")   # 兜底
# 实际用哪个模型由 resolve_model_path(cfg) 决定 → models/faster-whisper-<whisper_model>
AUDIO_DIR      = os.path.join(BASE_DIR, "audio_temp")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "transcripts")
CONFIG_FILE    = os.path.join(BASE_DIR, "config.json")
LOG_DIR        = os.path.join(BASE_DIR, "logs")
```

**→ 零硬编码绝对路径、零跨项目引用、零凭据。**

## 五、目录

```
voice_tool/
├── docs/                ← 本目录（2026-10-03 新建 · 2026-10-09 补三份）
├── misc/                ← 备用区（空）
├── voice_ball.py        ← 🔴 主程序（1,485 行 / 76,173 B）
├── voice_agent.py         命令行版（141 行 / 4,844 B）
├── 启动语音悬浮球.bat       ← 唯一日常入口（双击）
├── config.json            五个字段（含 ball_pos / language）
├── services.yaml  README.md  LICENSE  requirements.txt  .gitignore
├── models/              🔴 3,152 MB —— **两个模型**：medium + large-v3-turbo（**依赖，不是数据**）
├── audio_temp/          🔴 5,270 MB —— 4,413 个 wav（**用户的原始录音**）
├── transcripts/         🔴 1.81 MB —— 4,367 条转写（**用户每天说的话**）
├── logs/                   3.09 MB —— 轮转日志（2 文件）
├── venv/                🔴 3,047 MB
├── __pycache__/
└── .git/                    1 commit（工作区有未提交改动）
```

> **数字全部为 2026-10-09 实测。**（此前一版记的是 2026-10-03 的数字 —— `audio_temp` 六天涨了 1.2 GB。）

> **本项目不建 `src/`、不建 `data/`** —— 理由见 [log.md](log.md) 第二节。
> 简言之：**搬代码要改 `.bat` + 5 处路径常量；而它已经有三个语义清晰的数据目录了。**

## 七、输入槽

> **2026-10-03 补充段新增。**

### 7.1 结论：**无对外输入槽**

**本项目不接受任何来自【别的程序】的数据输入。**
**按 `project_manager/docs/INTERFACES.md` 第二章的定义（"项目接受输入的入口"），它没有输入槽。**

**它的输入全部来自人：**

| 输入 | 从哪来 | 是槽吗 |
| --- | --- | --- |
| **声音** | **物理麦克风**（`pyaudio`，MME/WASAPI 通路，见 [run.md](run.md)） | ❌ **不是** —— 是硬件采集，不是程序间接口 |
| **点击** | 用户点悬浮球（`voice_ball.py:1263-1269`，`mouseReleaseEvent` → `controller.toggle()`） | ❌ **不是** —— 是人机交互 |
| **热键** | 全局热键 `Ctrl+Alt+Space`（`voice_ball.py:1533-1548`，pynput） | ❌ **不是** —— 同上 |

### 7.2 ⚠️ 但有一个**事实上的、未声明的**外部输入口：`config.json`

| 项 | 内容 |
| --- | --- |
| **路径** | `D:\MyProject\voice_tool\config.json`（**163 B**，2026-10-09 实测） |
| **谁能写** | **同机任何进程，或人用记事本改** |
| **为什么算** | **它是"程序外能改变这个应用行为"的唯一一条路** |
| **同类** | 与 `Note` 的 `%APPDATA%\...\config\seasons.json` 热重载、`Workbench` 的 `config\tools.json` **是同一类东西** |
| 🔴 **但它【不是】槽** | **按定义不是** —— 它不承载"数据"，它改的是**本项目自己的行为参数** |

**五个字段，各自改什么行为（逐个核过源码，2026-10-09 复核）**：

| 字段 | 实测值 | 改它会怎样 | 在 `voice_ball.py` 里 | 在 `voice_agent.py` 里 |
| --- | --- | --- | --- | --- |
| **`hotkey`** | `"<ctrl>+<alt>+<space>"` | 换全局热键 | ✅ **生效** —— `normalize_hotkey(cfg.get("hotkey",""))` | ✅ 生效 |
| **`mic_device`** | `null`（自动选） | 手动指定麦克风（`{"host_api":…,"device":…}`） | ✅ **生效** —— 探测排序 + 子菜单勾选 | ❌ **不认识这个字段** |
| **`ball_pos`** | `[1041, 8]` | 悬浮球在屏幕上的位置 | ✅ **生效** —— 启动读、退出时写回 | ❌ 不认识 |
| ✅ **`whisper_model`** | `"large-v3-turbo"` | **换模型档位** | ✅ **生效** —— `resolve_model_path(cfg)` 拼出 `models/faster-whisper-<值>`；目录不存在则回退 medium | ✅ **也生效** —— 直接当模型名传给 `WhisperModel` |
| ✅ **`language`** | `"zh"` | 转写语言；写 `"auto"` 让模型自判 | ✅ **生效** —— `_transcribe_kwargs()` | ❌ 不认识 |

> ✅ **`whisper_model` 曾经是死字段，2026-10-09 已修好。**
> **旧版**：`:51` 把模型路径写死成 `models/faster-whisper-medium`，配置里那个值放进默认值后**再无引用** ——
> **改它对悬浮球毫无影响**（`voice_agent.py` 反而认）。
> **现在**：新增 `resolve_model_path(cfg)`，按配置拼路径，**两个入口都认了**；
> 目录不存在时**打 WARNING 并回退 medium，不崩**。

### 7.3 一句话

> **`voice_tool` 的输入是【人的声音和手指】，不是别的程序。**
> **它唯一一个"程序外能改行为"的入口是 `config.json` —— 五个字段现在【全部生效】。**
> 🔴 **槽文档已按 §8 拆开写：输入 [INPUT-SLOT.md](INPUT-SLOT.md) · 产出 [OUTPUT-SLOT.md](OUTPUT-SLOT.md)。**
> ⚠️ **§8 要求三份槽 —— 本项目还缺 `TRIGGER-SLOT.md`**（控制流暂时记在两个槽的 `## 详情` 里）。

---

## 八、产出清单

> **2026-10-03 补充段新增**（服务"七样说明"的第 4 样：**产生哪些结果**）。
> **此前这些产出散在 `data.md` 与本文第五节里，没有一张表收拢。**
>
> 🔴 **2026-10-09**：按 `CLAUDE.md` §7 拆出了正式的槽文档（**2026-10-11 已改造成 §8.4 固定格式**）
> **[OUTPUT-SLOT.md](OUTPUT-SLOT.md)**（每样产出按"产出物/落在哪/格式/怎么取/谁在用"五项写全，
> 判据是**消费者不读源码就能用**）。**本节保留为叙述性总览；字段级细节以槽文档为准。**

### 8.1 六样产出

| # | 产出 | 位置 | 格式 | 谁消费 | 可不可再生 |
| --- | --- | --- | --- | --- | --- |
| **1** | 🔴 **剪贴板** | **系统剪贴板**（无路径） | 纯文本 | 🔴 **人**（粘到任何地方）+ **任何程序** | ✅ 每次转写重写 |
| **2** | **转写存档** | `transcripts\{YYYYMMDD_HHMMSS}.txt` | UTF-8 纯文本 | 🔴 **人**（实测**全工程零外部消费者**） | ❌ **不可再生** —— `_rollback` 里**永久保留** |
| **3** | **原始录音** | `audio_temp\{同名}.wav` | 16-bit PCM，16k 或设备原生率 | ❌ **无消费者** | ❌ **不可再生**（是**他的声音**） |
| **4** | **运行日志** | `logs\voice_ball.log`（+`.1`..`.3`） | 文本，`RotatingFileHandler` 2 MB × 3 | 人（排查用） | ✅ 可清 |
| **5** | **本地配置** | `config.json` | JSON，4 字段 | **本程序自己**，下次启动读回 | ✅ 可重建（重调球位置） |
| **6** | 🔴 **注册表自启项** | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\VoiceBall` | `REG_SZ`，**两个绝对路径** | **Windows 登录时** | ✅ 可重建（`set_autostart(True)`） |

### 8.2 三句必须一起说的话

1. 🔴 **第 1 项（剪贴板）是本项目【唯一出工程】的交付。**
   下表六项里，**只有它离开了这个项目**（其余五项都落在项目内的目录或本机注册表里）。
   🔴 **而它：无声明 · 无版本 · 无格式约定 · 无法约束** ——
   **同机任何程序都能读写它，任何一次复制都会覆盖它，没有任何机制能约定"这里面是什么"。**
   **→ 它承载了这个工具存在的全部理由**（根 README：「文字已经在剪贴板里了，直接粘到任何地方」），
   **却没有任何一处文档能约束它。**
   **→ 已列进 `project_manager\docs\SLOT-CASCADE.md` 第八节「待议：系统级槽」（状态：待议，不拍板）。**
2. 🔴 **第 2、3 项是【不可再生】的**（他的声音、他每天说的话）——
   而它们的体积比是 **1 MB : 4 GB**（文本远小于音频）。
3. **第 6 项是唯一往项目外写的东西** —— 而且它的值是**绝对路径**（搬动即静默失效，见第三节）。

### 8.3 一句话

> **它产出六样东西。**
> **其中一样（剪贴板）没有任何文档形态，却承载了这个工具的全部目的；**
> **另一样（`audio_temp\`）没有任何消费者，却占了 4 GB。**

---

## 九、构建过程

> **2026-10-03 补充段新增**（"七样说明"的第 6 样）。
> 🔴 **本节的结论是：「没有可记的构建过程」。**

### 9.1 🔴 它的开发史【没有文档】

| 项 | 实测 |
| --- | --- |
| **`.git` 里的 commit 数** | 🔴 **1 个**（`ab32579`「语音悬浮球：点击录音、本地转写、自动复制到剪贴板」） |
| **工作区状态** | 7 条未跟踪（`docs\` 六份 + `services.yaml`）—— **都是整理产物，不是开发记录** |
| **开发日志** | 🔴 **没有**（不像 `Note` 有 `DEVELOPMENT_LOG.md`） |
| **CHANGELOG** | 🔴 **没有** |
| **根 `README.md`** | 有「快速开始 / 功能 / 已知限制」，**但没有"怎么一步步变成今天这样"** |

**→ 它把整个开发过程压进了【一个 commit】。**
**→ 中间改过什么、踩过什么、为什么这么设计，**版本控制里查不到**。**

### 9.2 ⚠️ 但代码注释里**能拼出一点线索**（**注明：从注释推的，不是日志**）

**`voice_ball.py` 的注释里有多处提到"以前/旧版/曾用"：**

| 线索 | 出处 | 说明 |
| --- | --- | --- |
| 「**旧版用 MME/16000 单声道录的音，转写 100% 正确**……**新版改优选 WASAPI 后**……」 | `:194-198` | **有过一次"MME → WASAPI 优选的改动"，并且改坏了，又改回 MME 优先** |
| 「**以前这里只 `print()`**，而 `pythonw` 下 stdout 是丢弃的，失败完全无声」 | `:1547` | **日志是后加的**（不是一开始就有） |
| 「**曾用它们拦**"WASAPI 单声道吐高频垃圾"……**实测环境噪声下极不稳定**……**结论：宁可放进一条平庸通路**」 | `:219-226` | **频谱门禁加过又撤了** |
| 「**历史 bug 就是异常路径直接 `return`**，泄漏的句柄把麦克风一直攥住」 | `:942-943` | **`finally` 是修 bug 修出来的** |
| 「**没有它的时候：开机自启动 + 手动点 bat 会叠出两个悬浮球**」 | `:1584-1586` | **单实例是后加的** |
| 「**之前用 PowerShell `Set-Content` 写回过一次**，带上 BOM 后被 json 解析失败、**静默退回默认配置（悬浮球位置就丢了）**」 | `:138-139` | **`utf-8-sig` 是修 bug 修出来的** |
| 「**过去这两种都只弹"未检测到声音，请检查麦克风"**，把用户引向了错误方向」 | `:968-969` | **错误提示分化是后加的** |
| 「**不立刻释放是为了让连着录几句时不必反复重载（每次约 3.5 秒）**」 | `:1034` | 闲置卸载的取舍 |

**→ 至少能推出 8 个迭代节点，但【推不出顺序】**（注释里只有"以前/曾/旧版"这种相对说法）。

### 9.3 本节**没有**做什么

| 没做 | 为什么 |
| --- | --- |
| ❌ **没有编一份开发日志** | **没有素材。编出来的历史比没有历史更坏。** |
| ❌ **没有从注释【断言】时间线** | 注释里**一处日期都没有**（`Note` 的 `DEVELOPMENT_LOG.md` 有 `§12（2026-09-17 追加）`这种标记，**这里没有**）。**推不出顺序。** |
| ✅ **只做了**：把"有哪些迭代痕迹"列出来，并**明确标注来源是注释** | —— |

### 9.4 一句话

> 🔴 **这是本工程第一个"构建过程【无据可查】"的项目。**
> **它的全部历史是 1 个 commit + 散落在代码里的 8 处"以前……"。**
> **→ 结论就是"没有"，不补。**

---

## 十、文档索引

| 文档 | 内容 |
| --- | --- |
| [README.md](README.md) | 本文件：定位 · 形态 · **自启的绝对路径陷阱** · 架构 · 目录 · **第七节 输入槽** · **第八节 产出清单** · **第九节 构建过程** |
| [run.md](run.md) | 三种跑法 · `config.json` · **自启怎么开关** · 已知限制 · **两个入口的差异表** |
| [data.md](data.md) | **为什么 `data/` 不建** · 三个数据目录 · 🔴 **5.15 GB 录音无自动清理** |
| [deps.md](deps.md) | 9 个包（钉死版本）· **对 `_shared` 的关系** · 无凭据 · **第五节 对外契约（含 `Workbench` 那条边）** · **第八节 麦克风通路自检** |
| [service.md](service.md) | 无常驻服务 · 但有常驻进程 · **自启是外部持久状态** |
| [INPUT-SLOT.md](INPUT-SLOT.md) | **我从哪拿**（§8.4 固定格式）—— 🔴 **固定表是空的**（本项目不从任何外部池子拿数据，理由在 `## 详情`）；五条"接近槽但不是"的东西逐条写全 |
| [OUTPUT-SLOT.md](OUTPUT-SLOT.md) | **我往外给**（§8.4 固定格式）—— **固定表 6 个锚点**：`transcripts` · `audio_temp` · `logs` · `config.json` · `services.yaml` · `models`。<br>🔴 **剪贴板与注册表自启项没有锚点**（进不了固定表），在 `## 详情` 里写全 |
| 🆕 [runtime-log.md](runtime-log.md) | **运行时行为**（可关）—— 启动序列 · 一次录音的状态耗时 · 资源占用 · 通路选择 · 热键看门狗 · 单实例 |
| [LESSONS.md](LESSONS.md) | **学到什么** —— 作者在代码注释里留下的教训 + 整理段的发现；**并列出没学到的空白** |
| [log.md](log.md) | 变更记录（**只追加**）—— 2026-10-03 整理 + 2026-10-09 补充 |
| **`README.md`（仓库根）** | 项目自己那份（含功能表与已知限制）—— **其中一句已过期**，见 [run.md](run.md) |
