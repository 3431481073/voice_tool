# 依赖

**Python 单栈。没有 Node、没有 `node_modules`。**

---

## 一、结论先行

| 问题 | 答案 |
| --- | --- |
| **有第三方 Python 包吗** | **有，9 个** —— ✅ **`requirements.txt` 钉死版本** |
| **有模型文件吗** | **有，在项目内** —— **两个**：`models/faster-whisper-medium/`（1,459.7 MB）+ `models/faster-whisper-large-v3-turbo/`（1,542.9 MB），共 **3.08 GB** |
| **对 `_shared/models/` 的贡献** | ⚠️ **本轮不搬，只登记** —— 见第四节 |
| **对 `_shared/routes.yaml` 的贡献** | ⚠️ **同上** —— **不是"零贡献"，是"发现了但没搬"** |
| **外部可执行依赖** | **无**（不需要 ffmpeg 之类） |
| **外部资源依赖** | **无**（模型在项目内） |
| **依赖其他项目吗** | **不依赖**（grep 零命中） |
| **有项目依赖它吗** | **没有** |
| **有凭据吗** | **没有** |

---

## 二、Python 依赖 —— 9 个，**全部钉死版本**

`requirements.txt`（330 B），**形态③**：

```
# 语音悬浮球 —— 直接依赖
# 版本取自本机 venv 实测（2026-09-30），非推测。

PySide6==6.11.2
faster-whisper==1.2.1
PyAudio==0.2.14
pynput==1.8.2
pyperclip==1.11.0
numpy==2.5.2

# faster-whisper 的 GPU 后端与 CUDA 运行库
ctranslate2==4.8.1
nvidia-cublas-cu12==12.9.2.10
nvidia-cudnn-cu12==9.25.1.1
```

| 包 | 用途 |
| --- | --- |
| `PySide6` | 悬浮球 GUI |
| `faster-whisper` | **转写引擎** |
| `ctranslate2` | faster-whisper 的推理后端 |
| **`nvidia-cublas-cu12` / `nvidia-cudnn-cu12`** | **CUDA 运行库** —— ctranslate2 用普通 `LoadLibrary` 加载，**只认 PATH**，所以代码里 `setup_cuda_path()` 会把它们的 `bin` 注进 PATH |
| `PyAudio` | 录音（MME / WASAPI） |
| `pynput` | 全局热键 |
| `pyperclip` | 写剪贴板 |
| `numpy` | 音频分析（波形、过零率、频谱重心） |

> ✅ **注释里写着「版本取自本机 venv 实测（2026-09-30），非推测」** ——
> **这是本工程里依赖清单写得第二好的**（第一是 `VideoKnowledgeBase`，它有 46 个包）。
> **对照**：`Kindred` **没有清单**、`OpenMontage` 有但用 `>=`。

**运行时**：`.venv` 实测 **Python 3.13.7**（`__pycache__` 里的 `.pyc` 是 `cpython-313`）。

> ⚠️ **顺带一条**：本机 PATH 上的 `python` **也是 3.13.7** ——
> 所以这次 `py_compile` 不会像 `VideoKnowledgeBase` 那次那样产生版本不一致的 `.pyc`。

---

## 三、外部可执行依赖

**无。** 不需要 ffmpeg、不需要别的二进制。

（对照：`VideoKnowledgeBase` 硬依赖 ffmpeg 且只能靠 PATH；`OpenMontage` 也是。
**本项目是自足的。**）

---

## 四、⚠️ 模型与 `_shared` —— **本轮不搬，只登记**

### 4.1 事实：**medium 至少有三份 + 本项目又添了一份 turbo**

| # | 位置 | `model.bin` |
| --- | --- | --- |
| **1** | **`voice_tool\models\faster-whisper-medium\`** | **1,527,906,378 B** |
| **2** | `video-workbench\.cache\models\faster-whisper-medium\` | **1,527,906,378 B** ← **字节数完全相同** |
| **3** | `D:\models\faster-whisper-medium` | **存在**（**项目外**，大小未读） |
| 🆕 **4** | **`voice_tool\models\faster-whisper-large-v3-turbo\`** | **1,617,884,929 B** —— **2026-10-04 新增**，是本项目当前的档位 |

**另有一份不同尺寸的**：`video-workbench\.cache\models\faster-whisper-large-v3\`（3,087,284,237 B）。

**还有几个 0 字节的空壳**（在 `catcher` 里，HF 缓存的占位）：
`catcher\backend\.cache\huggingface\hub\...\faster-whisper-{medium,small}\model.bin`、
`catcher\backend\dist\.cache\...\faster-whisper-medium\model.bin`。

**→ 共约 4.3 GB 花在同一个 medium 模型上**，**再加本项目的 turbo 1.5 GB**。

> 🔴 **2026-10-09 新增的这条**：本项目**又下了一份 large-v3-turbo**（1,542.9 MB）到项目内。
> **`_shared\models\asr\` 依然是空的** —— 也就是说，**同一个模型家族的第 N 份副本仍在增加**。
> **本轮只写文档，没搬、没链接。**

> ⚠️ **我没有做哈希比对** —— **"字节数完全相同"是强证据，不是证明。**

### 4.2 `_shared\routes.yaml` 里有一条正等着它的路由

```yaml
whisper-root:
  path: D:/MyProject/_shared/models/asr
  kind: whisper_download_root
  note: >-
    faster-whisper 的 download_root。各尺寸（tiny/base/small/medium/large-v3）
    都以 HuggingFace 缓存布局落在这一层，例如 models--Systran--faster-whisper-small/。
    消费者：BiliSearch（src/bili_search/routes.py 读取，config.whisper_root 暴露）。
  consumers: [BiliSearch]
```

**`_shared\models\asr\` 是空的。**

### 4.3 🔴 但**布局不一样**

| | 布局 |
| --- | --- |
| **`routes.yaml` 描述的** | `models--Systran--faster-whisper-medium/`（**HuggingFace 缓存布局**） |
| **`voice_tool\models\`** | `faster-whisper-medium\`（**裸目录，直接放 `model.bin`**） |

**而 `voice_tool` 的代码是 `WhisperModel(MODEL_DIR, ...)`，指向一个裸目录。**

**→ 要"只留一份"，得先决定 `_shared` 用哪种布局。**

### 4.4 本轮的处置：**不搬，只登记**

**三条理由：**

1. **代码直接指向 `models/faster-whisper-medium`** —— 搬它要改 `MODEL_DIR`（1 处），
   而**要先决定 `_shared` 用哪种布局**；
2. **那个模型有 3 份，其中一份在 `video-workbench`** —— **而 `video-workbench` 还没整理**。
   **"只留一份"是一个跨项目的决定**，按 PLAYBOOK 〇.1「一次只整理一个项目」，
   **不能在这一轮单独动**；
3. **它在跑、每天在用** —— **不值得为了省 1.4 GB 去动一个正在服务的模型路径**。

**→ 已列进 [log.md](log.md) 的未解决，等 `video-workbench` 那一轮一起谈。**

### 4.5 ⚠️ 附带发现：那条路由现在**没有活着的消费者**

`routes.yaml` 里写着 `consumers: [BiliSearch]` ——
**而 `BiliSearch` 已经归档消亡了**（在 `D:\MyProject\_archive\projects\BiliSearch\`）。

**→ 这条路由目前指向一个空目录、服务着一个不存在的项目。**
**也列进了未解决。**

---

## 五、对外契约表

| 方向 | 结果 |
| --- | --- |
| **本项目依赖别的项目吗** | ❌ **不依赖** —— grep `MyProject` / `catcher` / `video-workbench` / `_shared` / `shared_models`，**源码零命中** |
| **别的项目依赖本项目吗** | 🔴 **有 —— `Workbench`**（**2026-10-03 补充段改正**，原先写"没有"，见下） |

### 5.1 🔴 出向边：`Workbench` → `voice_tool`

**证据（`D:\MyProject\Workbench\config\tools.json`，2,198 B）**：

```json
{
  "id": "voice-ball",
  "emoji": "🎙",
  "svg_file": "icons/voice.svg",
  "label": "语音转文字",
  "action": "start D:\\MyProject\\voice_tool\\venv\\Scripts\\pythonw.exe D:\\MyProject\\voice_tool\\voice_ball.py"
}
```

**→ `Workbench` 的工具条里有一项「语音转文字」，它用【两个绝对路径】启动本项目。**

**断了会怎样**：**响亮失败**（点下去报"找不到文件"）—— 因为它是 `start` 一个不存在的路径。

**顺带**：`Workbench\README.md:63` 也把这一条列进了它的工具条表。

### 5.2 ⚠️ 但两边对同一条边【用了不同的词】—— 两边各写各的

| 侧 | 怎么写的 | 出处 |
| --- | --- | --- |
| **`Workbench`** | 把它列进 **"被登记"**，并明确写「**那不是"依赖"，是"被登记"**」 | `Workbench\services.yaml:32` |
| **`voice_tool`** | 原先写「**别的项目依赖本项目吗 → ❌ 没有**」 | 本文件（2026-10-03 前） |
| **工程级** | 把它记成一条**工具条项**（和 `Note` / `service-manager` / `video-panel` / `Lattice` / `markdown-reader` 并列） | `_rollback\README.md:268` |

> 🔴 **三种说法都不算错，但合起来就出了漏洞**：
> **`Workbench` 说"这不是依赖"、`voice_tool` 说"没人依赖我" ——
> 而实际上【有一条边，两边都没有把它当成边来记】。**
>
> **→ 这正是 `SLOT-CASCADE.md` 待议第 7 条说的「跨项目的事实没有唯一的家」。**

### 5.3 除此之外

> ⚠️ **"模型重复"那条不是"依赖"** —— 它是**共用同一份资源**，**记在第四节，不记在这里。**
>
> **其余项目提到 `voice_tool` 的地方（实测窄扫 219 个 `.md`/`.yaml`）都不是消费关系**：
> `video-workbench`（5 处）与 `genmedia-studio`（4 处）只是提到它**占 GPU** 与文件时间戳异常；
> `catcher`（2 处）只是形态对照与模型份数。**→ 详见 `project_manager\docs\log.md`。**

---

## 六、凭据

> **本项目没有凭据，音频与文本都不出机器。**

| 检查 | 结果 |
| --- | --- |
| `.env` | ❌ 不存在 |
| `config.json` | 只有 `whisper_model` / `hotkey` / `ball_pos` / `mic_device` / `language` —— **无密钥** |
| API Key | ✅ **零命中** —— **全部推理在本机**（faster-whisper + CUDA，不调任何云服务） |
| `.gitignore` | ✅ 已有「敏感面兜底（发布协议要求）」一节（`.env` / `*.db` / `*.key` / `id_rsa*` 等） |

**→ PLAYBOOK 步骤 6 的两条分支（凭据在项目内 / 在项目外）本项目都不适用。**

**`config.json` 没有被 `.gitignore` 挡住** —— 所以它是**入库的**。**这是对的**（里面没有秘密）。

---

## 七、环境位置

| 环境 | 位置 | 可重建？ |
| --- | --- | --- |
| **`venv\`** | 仓库根，**2,905.64 MB / 9,228 文件** | ✅ **可精确重建**（`requirements.txt` 钉死版本）—— 但要重下 CUDA 包 |
| `models\` | 仓库根，**1,459.67 MB** | ✅ 可重新下载（README 明说） |
| `__pycache__\` | 1 文件（`voice_ball.cpython-313.pyc`） | ✅ 自动 |

---

## 八、🔴 麦克风通路自检 —— `voice_ball.py` 里最重的一块

> **2026-10-03 补充段新增。**
> **它是全文件最大的一块**（`:164-664`，约 500 行），**也是作者写得最细的一块**。
> **此前文档只在功能表里有一行**（"逐条探测 MME / DirectSound / WASAPI，识别死路并自动回退"）——
> **这一节把【判据、优先级、以及为什么】写下来。**

### 8.1 为什么需要这一层

**原文**（`:181-186`）：

> `pa.open()` 不指定 `input_device_index` 时会落在 pyaudio 的默认 host API(MME)。
> **实测这台机器上 MME/WASAPI 都曾整条返回数字静音（峰值 1/32768），而 `pa.open()` 并不抛异常** ——
> 程序以为在录，实际录了一路零，最后只能弹"未检测到声音，请检查麦克风"，**把用户引向完全错误的方向**。
> 所以必须在运行时探测每条通路，并**从数据本身判断它是不是死的**。

### 8.2 通路的优先级

| 常量 | 值 | 出处 |
| --- | --- | --- |
| **`HOST_API_RANK`** | **`MME:0` · `WASAPI:1` · `DirectSound:2` · `WDMKS:3`**（**数字小 = 先试**） | `:199-204` |
| `HOST_API_TYPE_MME` / `_DIRECTSOUND` / `_WASAPI` / `_WDMKS` | `2` / `1` / `13` / `11` | `:187-190` |
| 🔴 **为什么 MME 排第一（反直觉）** | 「**旧版用 MME/16000 单声道录的音，转写 100% 正确**；**新版改优选 WASAPI 后**，同一条麦克风的 WASAPI 通路要么吐高频垃圾，要么不同窗口下量到的频谱忽好忽坏。**本机 Realtek 的 WASAPI 采集不可靠，MME 反而是稳的。**」 | `:194-198` |
| `VIRTUAL_DEVICE_HINTS` | `transcreen` · `立体声混音` · `stereo mix` · `声音映射器` · `sound mapper` · `主声音捕获` · `primary sound capture` · `virtual` · `虚拟` · `loopback` · `cable` —— **命中的设备排到最后** | `:207-209` |

### 8.3 死路判据（**全部用本机真实数据标定**）

**电平类 —— 用它们做门禁**：

| 常量 | 值 | 含义 | 出处 |
| --- | --- | --- | --- |
| **`DEAD_PEAK_MAX`** | **`4`** | 峰值 ≤ 4 → **数字静音**（对照：健康环境音**峰值 313+**） | `:215` |
| **`DEAD_SD_MIN`** | **`2.0`** | 标准差 < 2 → **锁死**（对照：健康环境音**标准差 33~96**） | `:216` |
| **`DEAD_DC_ABS`** | **`500.0`** | \|均值\| > 500 → **直流锁死的畸形缓冲区** | `:217` |

**→ `classify_stats()`（`:341-353`）只用这三条判 `ok / silence / dc / empty`。**

**🔴 频谱类 —— 只写日志，不做门禁**：

| 指标 | 说明 | 出处 |
| --- | --- | --- |
| `zero_cross_ratio` | 过零率 ÷ 采样率（**与采样率无关，可跨通路比较**） | `:316-320` |
| `spectral_centroid` | 谱质心（Hz）。**窗口取到 1 秒** —— 「用 0.4 秒短窗量环境噪声时结果会在 700~2000Hz 之间乱跳，同一通路两次测量能差一倍」 | `:323-338` |
| 🔴 **为什么不做门禁** | 「曾用它们拦"WASAPI 单声道吐高频垃圾"（过零比 0.178、谱质心 2250Hz，对比好通路 0.069~0.084、426~715Hz），想法成立，但**实测环境噪声下极不稳定** —— 同一条 MME 通路两次量到过零比 0.213/0.098、谱质心 1761/1815/426Hz。**结果是把好通路误判成垃圾、直接"没有可用通路"，比音质差严重得多。**」 | `:219-226` |

> **结论原文**：「**宁可放进一条平庸通路，也不要用会抖的指标去否决通路。**」

### 8.4 判定前必须跳过"零填充"

| 常量 | 值 | 出处 |
| --- | --- | --- |
| **`WARMUP_S`** | **`0.7`** | `:233` —— **至少读这么久才开始判定** |
| **`JUDGE_MAX_S`** | **`1.4`** | `:234` —— **最多读这么久：要么读到信号，要么判定为死路** |

**为什么**（`:228-232`）：「新开的流前面有一大段零填充。**逐缓冲区实测（前 40 个缓冲区）**：
MME 16000 前 6 个缓冲区为 1，第 7 个起 356 424…（**≈384ms**）；MME 44100 前 18 个为 1（**≈414ms**）；WASAPI 前 19 个为 0（**≈400ms**）。
**所以判定之前必须先把这段读过去，否则会把好设备误判成死的。**」

### 8.5 死路原因的五种人话（`DEAD_REASON_TEXT`，`:236-243`）

`silence`「通路返回数字静音」· `dc`「通路返回畸形数据（直流锁死）」· `garbage`「通路返回高频垃圾（通道/采样率组合不被驱动支持）」·
`bogus`「通路返回速度远超实时（不是在真正采集）」· `empty`「通路没有返回任何数据」· `error`「通路打开失败」

### 8.6 探测流程

```
list_input_devices()            :246-280   枚举输入设备（带 hostApi / 是否默认 / 是否虚拟）
   ↓
MicPath.open_attempts()         :380-405   按优先级给 (通道数, 采样率) 组合：
                                           ① (1, 16000)  ← 本机实测唯一"转写 100% 正确"的配置
                                           ② (1, 原生率)
                                           ③ (原生通道数, 原生率)  ← 兜底
                                           ④ (2, 原生率)          ← 设备号称单声道时也试一次
   ↓
MicManager.probe() / _open_validated()      :557-610  打开 → 读 WARMUP_S → 判定 → 记录 verdict
   ↓
MicManager.resolve(exclude=bad)             :611-633  挑出第一条通过的通路（PROBE_CAP = 5，最多试 5 条）
   ↓
MicManager.open_healthy_stream(exclude=)    :634-663  返回 (stream, path, preroll, reason)
```

**三条实现上的讲究**：

| # | 讲究 | 出处 |
| --- | --- | --- |
| **1** | 🔴 **`MicManager` 常驻一个 PyAudio 实例**，不每次录音新建/terminate —— 「反复初始化 PortAudio 并开关 Realtek 采集端点，**正是触发端点卡在"推零"状态的诱因之一**」 | `:409-412` |
| **2** | 🔴 **绝不在 GUI 线程初始化 PortAudio** —— 「会和后台探测线程争 `Pa_Initialize` 直接把进程打崩」。所以菜单只用 `snapshot_paths()` 的缓存 | `:1308-1311` |
| **3** | **`bad` 集合**（`:423`）—— 本次已判定死路的 `(host_api_index, device_index)`，**后续不再重试** | `:423` `:910` |

### 8.7 它解决的问题，本身就是一条教训

🔴 **"没检测到声音"和"麦克风通路坏了"曾经是同一句话** ——
现在用实测数据分开报（`:968-981`）：
前者是「**未检测到有效语音（峰值 …，通路 …）**」，后者是「**麦克风通路异常：未收到任何信号（峰值 …，标准差 …，通路 …）**」。
**→ 详见 [LESSONS.md](LESSONS.md) 第 12 条。**
