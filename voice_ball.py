# -*- coding: utf-8 -*-
"""
语音悬浮球 —— 语音转文字桌面工具
- 默认暂停状态，点击开始录音（实时波浪反馈）
- 再点一下停止并自动转写
- 转写完成自动复制到剪贴板 + 保存到 transcripts 文件夹
- 拖拽移动，右键菜单退出
"""

import os
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import sys
import math
import time
import wave
import json
import glob
import site
import logging
import logging.handlers
import threading
import winreg


def setup_cuda_path():
    """把 pip 安装的 nvidia CUDA 运行库目录加入 PATH，供 ctranslate2 使用。"""
    added = []
    try:
        for sp in site.getsitepackages():
            for d in glob.glob(os.path.join(sp, 'nvidia*')):
                if os.path.isdir(d):
                    for root, subdirs, files in os.walk(d):
                        if 'bin' in subdirs:
                            bin_dir = os.path.join(root, 'bin')
                            if os.path.isdir(bin_dir) and bin_dir not in added:
                                os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
                                added.append(bin_dir)
    except Exception:
        pass
    return added


setup_cuda_path()

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models", "faster-whisper-medium")
AUDIO_DIR = os.path.join(BASE_DIR, "audio_temp")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "transcripts")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "voice_ball.log")

log = logging.getLogger("voice_ball")


def setup_logging():
    """所有诊断信息必须落盘。

    pythonw.exe 没有控制台，print() 会被直接丢弃 —— 出问题时零线索。
    历史教训：用户看到过疑似"400"的报错但无从查证，就是因为没有日志。
    """
    if log.handlers:
        return
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s %(message)s")
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except Exception:
        pass

    def _hook(exc_type, exc, tb):
        log.critical("未捕获异常", exc_info=(exc_type, exc, tb))

    sys.excepthook = _hook
    threading.excepthook = lambda a: log.critical(
        "线程未捕获异常 (%s)", a.thread.name,
        exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


setup_logging()

try:
    import numpy as np
    import pyperclip
    import pyaudio
    from faster_whisper import WhisperModel
except Exception:
    # 依赖导入失败在 pythonw 下是完全静默的，必须记下来
    log.critical("关键依赖导入失败", exc_info=True)
    raise

from PySide6.QtCore import (Qt, QObject, Signal, QTimer, QPoint, QPointF,
                            QRectF, QSize, QPropertyAnimation)
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QRadialGradient,
                           QFont, QFontMetrics, QPixmap, QIcon, QGuiApplication)
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# ----------------------------------------------------------------------------
# 音频参数
# ----------------------------------------------------------------------------
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
SAMPLE_WIDTH = 2  # paInt16
NOISE_GATE = 0.019  # 音量低于此值视为静音，波浪不动（过滤环境噪声）
GAIN = 5.5          # 灵敏度增益：越大越灵敏，波浪越容易跳起来
TAIL_S = 0.6        # 点停止后继续收尾音的时长，避免最后几个字被驱动缓冲吞掉
IDLE_UNLOAD_S = 300  # 转写结束后多久自动释放模型（5 分钟），把约 1.9GB 显存还回去

# 悬浮球尺寸
BALL_R = 33          # 球体半径
PAD = 20             # 阴影/光晕留白
W = BALL_R * 2 + PAD * 2

# 配色
ACCENT_IDLE = QColor("#5b6cff")   # 待机：靛蓝
ACCENT_REC = QColor("#ff4d5e")    # 录音：红
ACCENT_WORK = QColor("#4d9fff")   # 转写：蓝
FG = QColor("#ffffff")


def load_config():
    default = {"whisper_model": "medium", "ball_pos": None, "mic_device": None}
    cfg = {}
    try:
        # utf-8-sig：容忍带 BOM 的文件。之前用 PowerShell Set-Content 写回过一次，
        # 带上 BOM 后被 json 解析失败、静默退回默认配置（悬浮球位置就丢了）。
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception:
        log.warning("配置文件读取失败，使用默认配置：%s", CONFIG_FILE, exc_info=True)
        cfg = {}
    for k, v in default.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_transcript(timestamp, text):
    filepath = os.path.join(TRANSCRIPT_DIR, f"{timestamp}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)


def compute_level(data):
    """由 int16 音频帧计算音量等级 0~1。"""
    try:
        arr = np.frombuffer(data, dtype=np.int16)
    except Exception:
        return 0.0
    if arr.size == 0:
        return 0.0
    peak = float(np.max(np.abs(arr))) / 32768.0
    rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2))) / 32768.0
    level = peak * 0.5 + rms * 0.5
    return min(1.0, level * GAIN)


# ----------------------------------------------------------------------------
# 麦克风采集通路：显式选路 + 死路检测 + 自动回退
#
# 为什么需要这一层：pa.open() 不指定 input_device_index 时会落在 pyaudio 的默认
# host API(MME)。实测这台机器上 MME/WASAPI 都曾整条返回数字静音（峰值 1/32768），
# 而 pa.open() 并不抛异常 —— 程序以为在录，实际录了一路零，最后只能弹"未检测到
# 声音，请检查麦克风"，把用户引向完全错误的方向。所以必须在运行时探测每条通路，
# 并从数据本身判断它是不是死的。
# ----------------------------------------------------------------------------
HOST_API_TYPE_MME = 2
HOST_API_TYPE_DIRECTSOUND = 1
HOST_API_TYPE_WASAPI = 13
HOST_API_TYPE_WDMKS = 11

# 通路优先级。这是"先试谁"，最终仍由实测频谱把关。
#
# 为什么 MME 排第一而不是 WASAPI（反直觉，但有本机实测依据）：
#   旧版用 MME/16000 单声道录的音，转写 100% 正确（"就是我打开好像它上面有个音量…"）；
#   新版改优选 WASAPI 后，同一条麦克风的 WASAPI 通路要么吐高频垃圾（单声道，
#   过零比 0.178 / 谱质心 2250Hz），要么在不同窗口下量到的频谱忽好忽坏。
#   本机 Realtek 的 WASAPI 采集不可靠，MME 反而是稳的。
HOST_API_RANK = {
    HOST_API_TYPE_MME: 0,
    HOST_API_TYPE_WASAPI: 1,
    HOST_API_TYPE_DIRECTSOUND: 2,
    HOST_API_TYPE_WDMKS: 3,
}

# 这些名字不是真实麦克风，排到最后
VIRTUAL_DEVICE_HINTS = ("transcreen", "立体声混音", "stereo mix", "声音映射器",
                        "sound mapper", "主声音捕获", "primary sound capture",
                        "virtual", "虚拟", "loopback", "cable")

# ---- 死路判据（全部用本机真实数据标定）------------------------------------
# 电平类：拦"没有信号"
#   数字静音   : 峰值 1     标准差 0.5              <- MME/WASAPI 端点卡死时
#   健康环境音 : 峰值 313+  标准差 33~96
DEAD_PEAK_MAX = 4        # 峰值 <= 4 视为数字静音
DEAD_SD_MIN = 2.0        # 标准差 < 2 视为锁死
DEAD_DC_ABS = 500.0      # |均值| > 500 视为直流锁死的畸形缓冲区

# 频谱类指标（谱质心、过零率）只写日志、不做门禁。
#
# 走过一次弯路：曾用它们拦"WASAPI 单声道吐高频垃圾"（过零比 0.178、谱质心 2250Hz，
# 对比好通路 0.069~0.084、426~715Hz），想法成立，但实测**环境噪声下极不稳定** ——
# 同一条 MME 通路两次量到 过零比 0.213/0.098、谱质心 1761/1815/426Hz。
# 结果是把好通路误判成垃圾、直接"没有可用通路"，比音质差严重得多。
# 结论：宁可放进一条平庸通路，也不要用会抖的指标去否决通路。
# 真正的解法是优先用已验证能正确转写的配置（见 HOST_API_RANK 与 open_attempts）。

# 新开的流前面有一大段零填充。逐缓冲区实测（前 40 个缓冲区）：
#   MME 16000  : 前 6 个缓冲区为 1，第 7 个起 356 424 ...   ≈384ms
#   MME 44100  : 前 18 个为 1                        ≈414ms
#   WASAPI     : 前 19 个为 0                        ≈400ms
# 所以判定之前必须先把这段读过去，否则会把好设备误判成死的。
WARMUP_S = 0.7           # 至少读这么久才开始判定
JUDGE_MAX_S = 1.4        # 最多读这么久：要么读到信号，要么判定为死路

DEAD_REASON_TEXT = {
    "silence": "通路返回数字静音",
    "dc": "通路返回畸形数据（直流锁死）",
    "garbage": "通路返回高频垃圾（通道/采样率组合不被驱动支持）",
    "bogus": "通路返回速度远超实时（不是在真正采集）",
    "empty": "通路没有返回任何数据",
    "error": "通路打开失败",
}


def list_input_devices(pa):
    """列出全部输入设备，带上所在 host API 与"是否系统默认设备"标记。"""
    try:
        default_name = pa.get_default_input_device_info().get("name")
    except Exception:
        default_name = None
    out = []
    for i in range(pa.get_device_count()):
        try:
            d = pa.get_device_info_by_index(i)
        except Exception:
            continue
        if int(d.get("maxInputChannels", 0)) <= 0:
            continue
        api_idx = int(d.get("hostApi", -1))
        try:
            api = pa.get_host_api_info_by_index(api_idx)
            api_name = api.get("name", "?")
            api_type = int(api.get("type", -1))
        except Exception:
            api_name, api_type = "?", -1
        name = d.get("name", "?")
        low = name.lower()
        out.append({
            "device_index": i,
            "host_api_index": api_idx,
            "host_api_name": api_name,
            "host_api_type": api_type,
            "name": name,
            "default_rate": d.get("defaultSampleRate"),
            "max_input_channels": int(d.get("maxInputChannels", 1)),
            "is_default": (name == default_name),
            "virtual": any(h in low for h in VIRTUAL_DEVICE_HINTS),
        })
    return out


def mono_array(frames_bytes, channels=1):
    """把原始帧转成单声道 float 数组（多声道取平均）。

    频谱判据必须在单声道上算：交错的立体声数据直接做过零率会得到虚假的高频。
    """
    arr = np.frombuffer(b"".join(frames_bytes), dtype=np.int16)
    if arr.size == 0:
        return np.zeros(0)
    a = arr.astype(np.float64)
    if channels and channels > 1:
        n = (a.size // channels) * channels
        a = a[:n].reshape(-1, channels).mean(axis=1)
    return a


def audio_stats(frames_bytes, channels=1, rate=RATE, skip_s=0.0):
    """由原始帧算出判断通路死活所需的统计量。

    电平类(peak/mean/sd)用整段；频谱类(zcr/centroid)跳过开头的零填充再算，
    否则那段静音会把频谱特征稀释掉。
    """
    a = mono_array(frames_bytes, channels)
    if a.size == 0:
        return None
    st = {"peak": int(np.max(np.abs(a))), "mean": float(np.mean(a)),
          "sd": float(np.std(a)), "n": int(a.size)}
    seg = a[int(rate * skip_s):] if skip_s > 0 else a
    if seg.size >= 2048:
        st["zcr_ratio"] = zero_cross_ratio(seg, rate)
        st["centroid"] = spectral_centroid(seg, rate)
    return st


def zero_cross_ratio(x, rate):
    """过零率 ÷ 采样率。与采样率无关，可跨通路比较。"""
    if x.size < 2 or rate <= 0:
        return 0.0
    return float(np.count_nonzero(np.diff(np.signbit(x)))) / (x.size / float(rate)) / rate


def spectral_centroid(x, rate):
    """谱质心(Hz)。语音/环境噪声能量集中在低频，坏通路会吐高频垃圾。

    窗口取到 1 秒：用 0.4 秒短窗量环境噪声时结果会在 700~2000Hz 之间乱跳，
    同一通路两次测量能差一倍，判据就没法用了。
    """
    n = min(int(x.size), max(2048, int(rate * 1.0)))
    seg = x[:n]
    if seg.size < 2048:
        return 0.0
    S = np.abs(np.fft.rfft(seg * np.hanning(seg.size))) ** 2
    tot = float(S.sum())
    if tot <= 0:
        return 0.0
    f = np.fft.rfftfreq(seg.size, 1.0 / rate)
    return float((f * S).sum() / tot)


def classify_stats(st):
    """把统计量判成 ok / silence / dc / bogus / empty。

    只用电平类判据（峰值/标准差/直流）—— 它们无歧义且稳定。
    频谱类指标只记日志，不参与判定：环境噪声下它们抖动太大，会把好通路误杀。
    """
    if st is None or st.get("n", 0) == 0:
        return "empty"
    if abs(st["mean"]) > DEAD_DC_ABS:
        return "dc"
    if st["peak"] <= DEAD_PEAK_MAX or st["sd"] < DEAD_SD_MIN:
        return "silence"
    return "ok"


class MicPath:
    """一条候选采集通路（含最终确认可用的采样率/通道数）。"""

    def __init__(self, dev):
        self.device_index = dev["device_index"]
        self.host_api_index = dev["host_api_index"]
        self.host_api_name = dev["host_api_name"]
        self.host_api_type = dev["host_api_type"]
        self.name = dev["name"]
        self.is_default = dev["is_default"]
        self.virtual = dev["virtual"]
        self.default_rate = int(dev.get("default_rate") or RATE)
        self.max_ch = int(dev.get("max_input_channels") or 1)
        # 探测成功后填入实际可用的参数
        self.rate = RATE
        self.channels = CHANNELS

    @property
    def label(self):
        return f"{self.name} @ {self.host_api_name}"

    def key(self):
        return (self.host_api_index, self.device_index)

    def open_attempts(self):
        """按优先级尝试的 (通道数, 采样率) 组合。

        实测教训（本机 Realtek）：
          - WASAPI 不接受 16000（[Errno -9997] Invalid sample rate），要回退原生率；
          - 更要命的是，WASAPI 强行要单声道时会返回**高频垃圾**（过零率 8562/s、
            谱质心 2250Hz），必须按设备原生通道数（立体声）采集再自行降混。
        所以"单声道优先"之后紧跟着就是"原生通道数优先"。
        faster-whisper 会自动重采样并降混，录立体声/非 16k 都没问题。
        """
        nat = self.default_rate or RATE
        # 单声道 16k 放第一：这是本机实测唯一"转写 100% 正确"的配置（旧版就是它）。
        # 强行要单声道在 WASAPI 上会吐高频垃圾，但那是 WASAPI 的问题 ——
        # MME 单声道 16k 是稳的，而 MME 现在排第一，所以先试它。
        combos = [(CHANNELS, RATE)]
        combos.append((CHANNELS, nat))               # 单声道 + 原生率
        if self.max_ch > 1:
            combos.append((self.max_ch, nat))        # 兜底：设备原生通道数
        if self.max_ch == 1:
            combos.append((2, nat))                  # 设备号称单声道时也试一次立体声
        seen, out = set(), []
        for c in combos:
            if c not in seen and c[0] > 0 and c[1] > 0:
                seen.add(c)
                out.append(c)
        return out


class MicManager:
    """常驻一个 PyAudio 实例，负责挑出并打开一条真正有信号的采集通路。

    常驻而非每次录音新建/terminate：反复初始化 PortAudio 并开关 Realtek 采集
    端点，正是触发端点卡在"推零"状态的诱因之一。
    """

    PROBE_CAP = 5       # 自动探测最多试几条，避免启动长时间卡住

    def __init__(self, cfg):
        self.cfg = cfg
        self.pa = None
        self.devices = []
        self.chosen = None          # 当前生效的 MicPath
        self.chosen_stats = None
        self.bad = set()            # 本次已判定死路的 (host_api_index, device_index)
        self.auto = True            # 是否为自动选路（受 config 影响）
        self._lock = threading.RLock()

    # -- 生命周期 -----------------------------------------------------------
    def init(self):
        """创建 PyAudio 并枚举设备。必须持锁。

        实测教训：GUI 线程和探测线程同时调用 pyaudio.PyAudio()（即 PortAudio 的
        Pa_Initialize）会直接触发访问冲突 0xc0000005 把进程打死，日志里连 Python
        异常都不会有（native 崩溃）。所以这里必须串行化。
        """
        with self._lock:
            if self.pa is None:
                self.pa = pyaudio.PyAudio()
                log.info("PyAudio 初始化完成，版本 %s", pyaudio.__version__)
            if not self.devices:
                self.refresh_devices()

    def refresh_devices(self):
        """重新枚举设备。调用方须已持有锁。"""
        if self.pa is None:
            self.pa = pyaudio.PyAudio()
        self.devices = list_input_devices(self.pa)
        log.info("枚举到 %d 个输入设备：", len(self.devices))
        for d in self.devices:
            log.info("  [%2d] %-42s host=%-18s 默认=%s 虚拟=%s",
                     d["device_index"], d["name"], d["host_api_name"],
                     d["is_default"], d["virtual"])
        return self.devices

    def snapshot_paths(self):
        """只读已缓存的设备快照，绝不触碰 PortAudio。

        GUI 线程构建菜单只能走这里：在 GUI 线程上初始化 PortAudio 既会卡住界面，
        又会和后台探测线程争 Pa_Initialize 而导致硬崩溃。
        """
        return [MicPath(d) for d in list(self.devices)]

    def refresh_async(self):
        """后台重新枚举设备（插拔麦克风后用），不阻塞调用方。"""
        def work():
            try:
                with self._lock:
                    self.init()
                    self.refresh_devices()
            except Exception:
                log.error("重新枚举设备失败", exc_info=True)
        threading.Thread(target=work, daemon=True).start()

    def close(self):
        with self._lock:
            if self.pa is not None:
                try:
                    self.pa.terminate()
                except Exception:
                    log.warning("PyAudio terminate 失败", exc_info=True)
                self.pa = None

    # -- 候选排序 -----------------------------------------------------------
    def ordered_paths(self, exclude=()):
        """候选排序：手动覆盖 > 真实设备 > 与系统默认同名 > host API 优先级 > 虚拟设备。"""
        self.init()
        devs = [d for d in self.devices
                if (d["host_api_index"], d["device_index"]) not in exclude]

        override = self.cfg.get("mic_device")
        if isinstance(override, dict) and override.get("device"):
            hit = [d for d in devs
                   if d["host_api_name"] == override.get("host_api")
                   and d["name"] == override.get("device")]
            if hit:
                log.info("手动指定的麦克风生效：%s @ %s",
                         hit[0]["name"], hit[0]["host_api_name"])
                rest = [d for d in devs if d is not hit[0]]
                devs = hit + rest
            else:
                log.warning("手动指定的麦克风已不存在（%s @ %s），回落到自动探测",
                            override.get("device"), override.get("host_api"))

        def sort_key(d):
            return (
                0 if not d["virtual"] else 1,               # 真实设备优先
                HOST_API_RANK.get(d["host_api_type"], 9),   # WASAPI > MME > DS > WDM-KS
                0 if d["is_default"] else 1,                # 与系统默认同名优先
                d["device_index"],
            )

        return [MicPath(d) for d in sorted(devs, key=sort_key)]

    # -- 探测 ---------------------------------------------------------------
    def _read_window(self, stream, rate, ch, seconds):
        """读一段（含预热），返回 (帧列表, 实际耗时)。

        新开的流前面有约 400ms 零填充，读满 WARMUP_S 之后一旦发现真实信号就
        提前收工，健康通路通常 ~0.7s 就能确认。
        """
        need = max(1, int(rate * seconds / CHUNK))
        warm_bufs = max(1, int(rate * WARMUP_S / CHUNK))
        frames = []
        t0 = time.time()
        for i in range(need):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
            if (i + 1) >= warm_bufs and (i % 4 == 0):
                if classify_stats(audio_stats(frames, ch, rate, WARMUP_S)) == "ok":
                    break
        return frames, time.time() - t0

    def _judge(self, frames, rate, ch, elapsed):
        """判定一条通路是否可用，返回 (status, stats)。"""
        st = audio_stats(frames, ch, rate, WARMUP_S) or {}
        if st.get("n", 0) == 0:
            return "empty", st
        st["elapsed"] = elapsed
        expected = st["n"] / float(rate)
        # 实测 DirectSound 40 个缓冲区本该耗时 2.56s，却 0.04s 就返回 —— 它根本
        # 没在实时采集，只是吐 ±32000 的交替假数据。这个判据很硬。
        if expected > 0.2 and elapsed < expected * 0.5:
            return "bogus", st
        return classify_stats(st), st

    def _close_quiet(self, stream, what):
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            log.warning("关闭流失败（%s）", what, exc_info=True)

    def _log_verdict(self, path, st, status, combo):
        log.warning("淘汰 %s [%s]：%s（峰值=%s 均值=%s 标准差=%s 谱质心=%.0fHz 过零比=%.3f）",
                    path.label, combo, DEAD_REASON_TEXT.get(status, status),
                    st.get("peak"), st.get("mean"), st.get("sd"),
                    st.get("centroid", 0.0), st.get("zcr_ratio", 0.0))

    def _open_validated(self, path):
        """逐个尝试参数组合，返回第一条真正健康的流。

        必须是"逐个组合验证"，不能"打开成功就用" —— 实测本机 WASAPI 用单声道
        能正常打开、电平也正常，但拿到的是高频垃圾，只有频谱判据能识破。

        返回 (stream, rate, ch, 预读帧, stats, 失败原因)；成功时 stream 非 None，
        由调用方负责关闭。
        """
        last = "没有可用参数组合"
        for ch, rate in path.open_attempts():
            combo = f"ch={ch} rate={rate}"
            try:
                stream = self.pa.open(
                    format=FORMAT, channels=ch, rate=rate, input=True,
                    input_device_index=path.device_index,
                    frames_per_buffer=CHUNK)
            except Exception as e:
                last = f"{combo} 打开失败：{e}"
                log.debug("打开组合失败 %s %s：%s", path.label, combo, e)
                continue

            try:
                frames, elapsed = self._read_window(stream, rate, ch, JUDGE_MAX_S)
            except Exception as e:
                last = f"{combo} 读取失败：{e}"
                log.warning("读取失败 %s %s：%s", path.label, combo, e)
                self._close_quiet(stream, f"{path.label} {combo}")
                continue

            status, st = self._judge(frames, rate, ch, elapsed)
            if status == "ok":
                path.rate, path.channels = rate, ch
                st["status"] = "ok"
                log.debug("组合可用 %s %s（峰值=%d 谱质心=%.0fHz）",
                          path.label, combo, st["peak"], st.get("centroid", 0.0))
                return stream, rate, ch, frames, st, None

            self._log_verdict(path, st, status, combo)
            self._close_quiet(stream, f"{path.label} {combo}")
            last = DEAD_REASON_TEXT.get(status, status)
        return None, None, None, [], None, last

    def probe(self, path):
        """打开一条通路读够预热后判定。任何失败都转成字典，不抛异常。"""
        stream, rate, ch, frames, st, reason = self._open_validated(path)
        if stream is None:
            log.warning("探测打不开 %s：%s", path.label, reason)
            return {"error": reason}
        # 无论成败都必须释放。历史上 pa.open() 抛异常就直接 return，泄漏的句柄
        # 会把麦克风一直攥住，此后所有采集（含新实例）都变成数字静音。
        self._close_quiet(stream, f"探测 {path.label}")
        return st

    def resolve(self, exclude=()):
        """挑一条真正健康的通路并缓存。全部不可用返回 None。"""
        with self._lock:
            tried = 0
            for path in self.ordered_paths(exclude):
                if tried >= self.PROBE_CAP:
                    log.warning("已达探测上限 %d 条，停止探测", self.PROBE_CAP)
                    break
                tried += 1
                st = self.probe(path)
                if st.get("status") == "ok":
                    self.chosen, self.chosen_stats = path, st
                    log.info("选中采集通路：%s 采样率=%d 通道=%d 峰值=%d 均值=%.1f "
                             "标准差=%.1f 谱质心=%.0fHz",
                             path.label, path.rate, path.channels, st["peak"],
                             st["mean"], st["sd"], st.get("centroid", 0.0))
                    return path
                self.bad.add(path.key())

            self.chosen, self.chosen_stats = None, None
            log.error("没有找到可用的采集通路（已试 %d 条）", tried)
            return None

    def open_healthy_stream(self, exclude=()):
        """打开一条确认健康的流，返回 (stream, path, 预读帧, 失败原因)。

        预读的帧不能丢：它同时也验证了这条通路真的在给出可懂音频。
        """
        with self._lock:
            reason = "没有可用候选"
            tried = 0
            for path in self.ordered_paths(exclude):
                if tried >= self.PROBE_CAP:
                    break
                tried += 1
                stream, rate, ch, preroll, st, why = self._open_validated(path)
                if stream is None:
                    self.bad.add(path.key())
                    reason = f"{path.label} {why}"
                    continue

                self.chosen, self.chosen_stats = path, st
                log.info("录音使用通路：%s 采样率=%d 通道=%d"
                         "（预读 %d 帧 峰值=%d 均值=%.1f 标准差=%.1f 谱质心=%.0fHz）",
                         path.label, rate, ch, len(preroll), st["peak"],
                         st["mean"], st["sd"], st.get("centroid", 0.0))
                return stream, path, preroll, None

            self.chosen, self.chosen_stats = None, None
            log.error("没有打开任何可用采集通路（已试 %d 条）：%s", tried, reason)
            return None, None, [], reason


# ----------------------------------------------------------------------------
# 信号桥：后台线程 -> GUI 线程
# ----------------------------------------------------------------------------
class Bridge(QObject):
    level = Signal(float)            # 实时音量
    state_changed = Signal(str)      # loading / idle / recording / transcribing
    model_ready = Signal(str)        # 设备名 cuda / cpu
    transcribed = Signal(str)        # 转写结果
    error = Signal(str)              # 错误信息
    toggle_requested = Signal()      # 热键线程 -> GUI 线程，避免跨线程改状态
    mic_info = Signal(str)           # 麦克风诊断结果


class Controller:
    """负责模型加载、录音、转写，全部在后台线程运行。"""

    def __init__(self, bridge, cfg):
        self.bridge = bridge
        self.cfg = cfg
        self.model = None
        self.device = None
        self.model_loaded = False
        self.model_failed = False
        self._loading = False
        self._model_ready = threading.Event()
        self._idle_timer = None
        self._idle_lock = threading.Lock()
        self.mic = MicManager(cfg)
        self._state = "idle"
        self._state_lock = threading.Lock()
        self._recording = threading.Event()

        # 启动时不加载模型：省下约 1.9GB 显存给别的程序（比如 ComfyUI）。
        # 模型在第一次录音时与收音并行加载，转写完 5 分钟无人使用即自动释放。
        log.info("启动时不加载模型，首次录音时与收音并行加载，闲置 %d 秒后自动释放",
                 IDLE_UNLOAD_S)
        threading.Thread(target=self._warm_mic, daemon=True).start()

    # -- 初始界面状态 -------------------------------------------------------
    def initial_ui_state(self):
        """给悬浮球的初始显示状态。

        不能靠 Controller.__init__ 里 emit 一个 "idle" —— 那时悬浮球还没 connect
        信号槽，信号直接丢掉，球会卡在自己的初始 "loading" 态一直转圈，直到用户
        第一次点录制才被唤醒。这就是"刚打开空转很久"的根因。
        """
        if self.model_loaded or self.model_failed:
            return "idle"
        if self._loading:
            return "loading"
        return "idle"

    # -- 闲置自动释放 -------------------------------------------------------
    def _cancel_idle_unload(self):
        with self._idle_lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None

    def _schedule_idle_unload(self):
        """转写结束后开始倒计时；到点仍没人用就释放模型。"""
        self._cancel_idle_unload()
        with self._idle_lock:
            t = threading.Timer(IDLE_UNLOAD_S, self._idle_unload)
            t.daemon = True
            self._idle_timer = t
            t.start()
        log.info("已排定 %d 秒后自动释放模型", IDLE_UNLOAD_S)

    def _idle_unload(self):
        with self._idle_lock:
            self._idle_timer = None
        if self._get_state() != "idle" or self._recording.is_set():
            log.info("到点时有任务在跑，跳过自动释放")
            return
        self._unload_model()

    def unload_now(self):
        """手动关闭语音识别，立刻释放显存。"""
        self._cancel_idle_unload()
        if self.model is None:
            return False
        self._unload_model()
        return True

    def _unload_model(self):
        """释放模型与显存。

        ctranslate2 没有卸载 API，只能丢掉引用再强制回收。
        实测：加载 +1981MiB / 释放 −1888MiB / 残余仅 +93MiB，0.03 秒完成。
        """
        if self.model is None:
            return
        t0 = time.time()
        self.model = None
        self.model_loaded = False
        self._model_ready.clear()
        try:
            import gc
            gc.collect()
        except Exception:
            log.warning("gc.collect 失败", exc_info=True)
        log.info("模型已释放（耗时 %.2fs）", time.time() - t0)

    # -- 状态 ---------------------------------------------------------------
    def _set_state(self, s):
        with self._state_lock:
            changed = (self._state != s)
            self._state = s
        if changed:
            log.info("状态 -> %s", s)
            self.bridge.state_changed.emit(s)

    def _get_state(self):
        with self._state_lock:
            return self._state

    # -- 麦克风通路预热 -----------------------------------------------------
    def _warm_mic(self):
        """启动时就把通路探出来并写进日志，别等用户点了第一次才发现是死的。"""
        try:
            if self.mic.resolve() is None:
                self.bridge.error.emit("没找到可用的麦克风通路，录音会失败（详见日志）")
        except Exception:
            log.error("麦克风通路探测异常", exc_info=True)

    # -- 模型加载 -----------------------------------------------------------
    def ensure_model_loading(self):
        """确保模型正在加载，不阻塞调用方。

        非常驻模式下与录音并行执行，把 ~3.2s 的加载时间藏在用户说话的过程里，
        否则这 3.2s 会正好压在"开头几句话"上。
        """
        if self.model_loaded or self._loading:
            return
        threading.Thread(target=self._load_model, kwargs={"silent": True},
                         daemon=True).start()

    def _load_model(self, silent=False):
        """加载模型。silent=True 表示在录音期间后台加载，不要打扰界面。"""
        self._loading = True
        self._model_ready.clear()
        t0 = time.time()
        try:
            self.model = WhisperModel(MODEL_DIR, device="cuda", compute_type="float16")
            self.device = "cuda"
        except Exception:
            log.warning("CUDA 加载失败，回退 CPU", exc_info=True)
            try:
                self.model = WhisperModel(MODEL_DIR, device="cpu", compute_type="int8")
                self.device = "cpu"
            except Exception as e:
                self.model = None
                self.model_loaded = False
                self.model_failed = True
                self._loading = False
                log.error("模型加载彻底失败", exc_info=True)
                if not silent:
                    self._set_state("idle")
                self.bridge.error.emit(f"模型加载失败：{e}（详见日志）")
                return
        self.model_loaded = True
        self.model_failed = False
        self._loading = False
        self._model_ready.set()
        log.info("模型加载完成：device=%s 耗时=%.1fs%s",
                 self.device, time.time() - t0, "（录音期间后台加载）" if silent else "")

        if silent:
            # 录音/转写进行中，绝不能把界面切回 idle —— 否则球会在录音时显示待机
            return
        self._set_state("idle")
        self.bridge.model_ready.emit(self.device)

    def retry_model(self):
        """失败后的重试入口。否则用户每次点击都只会听到同一句"加载失败"。"""
        if self.model_loaded or self._loading:
            return
        self._load_model()

    def _wait_model(self, timeout=60.0):
        """等模型加载完（非常驻模式下录音结束时可能还在装）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.model_loaded:
                return True
            if self.model_failed:
                return False
            time.sleep(0.1)
        return self.model_loaded

    # -- 状态切换 -----------------------------------------------------------
    def toggle(self):
        state = self._get_state()
        if state == "idle":
            self.start_recording()
        elif state == "recording":
            self.stop_recording()
        else:
            log.info("当前状态 %s，忽略切换请求", state)

    def start_recording(self):
        if self._get_state() != "idle" or self._recording.is_set():
            return
        if self.model_failed:
            self.bridge.error.emit("模型加载失败过，正在重试…（详见日志）")
            threading.Thread(target=self.retry_model, daemon=True).start()
            return
        self._cancel_idle_unload()
        if not self.model_loaded:
            # 立刻起后台加载，与录音并行 —— 用户说话的这几秒足够把约 3.5s 的
            # 加载藏掉，不会像"先加载再录"那样吃掉开头几句话
            log.info("录音与模型加载同时开始")
            self.ensure_model_loading()
        self._recording.set()
        self._set_state("recording")
        threading.Thread(target=self._record_loop, daemon=True).start()

    def stop_recording(self):
        if self._recording.is_set():
            log.info("收到停止请求")
            self._recording.clear()
            # 界面立刻切走，不等尾音收完 —— 否则按下停止后还会红 0.6 秒，很"不跟手"。
            # 收尾音在后台继续（见 _record_loop 的 stop_at 逻辑），用户感觉不到。
            self._set_state("transcribing")

    def shutdown(self):
        self._recording.clear()
        self.mic.close()

    # -- 录音 + 转写 --------------------------------------------------------
    def _record_loop(self):
        """外壳：保证无论内部怎么炸，状态都不会卡在录音/转写态。"""
        try:
            self._record_loop_inner()
        except Exception:
            log.error("录音线程异常", exc_info=True)
            self.bridge.error.emit("录音异常中断（详见日志）")
            self._set_state("idle")

    def _record_loop_inner(self):
        frames = []
        stream = None
        path = None
        try:
            stream, path, preroll, reason = self.mic.open_healthy_stream(
                exclude=self.mic.bad)
            if stream is None:
                # 必须复位状态：stop_recording 会先把界面切到"转写中"，
                # 这里若直接 return，悬浮球会永远卡在转写态。
                self._set_state("idle")
                self.bridge.error.emit(f"麦克风通路异常：{reason}（详见日志）")
                return
            frames.extend(preroll)

            had_sound = any(compute_level(f) >= NOISE_GATE for f in preroll)
            stop_at = None
            while True:
                # 用户点停止后不要立刻跳出：驱动/PortAudio 缓冲里还有已经录到但
                # 没交出来的尾音（典型 100~400ms），立刻关流会把最后几个字扔掉。
                if not self._recording.is_set() and stop_at is None:
                    stop_at = time.time() + TAIL_S
                    log.info("收到停止请求，继续收取 %.1fs 尾音", TAIL_S)
                if stop_at is not None and time.time() >= stop_at:
                    break
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                except Exception as e:
                    log.error("录音中读取失败", exc_info=True)
                    self.bridge.error.emit(f"录音中断：{e}（详见日志）")
                    break
                frames.append(data)
                lvl = compute_level(data)
                if lvl >= NOISE_GATE:
                    had_sound = True
                if stop_at is None:
                    self.bridge.level.emit(lvl)
        finally:
            # 无论走哪条路径都要释放：历史 bug 就是异常路径直接 return，
            # 泄漏的句柄把麦克风一直攥住，此后所有采集都是数字静音。
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    log.warning("关闭录音流失败", exc_info=True)
            self._recording.clear()

        label = path.label if path else "?"
        rate = path.rate if path else RATE
        ch = path.channels if path else CHANNELS
        st = audio_stats(frames, ch, rate, WARMUP_S)
        if st is None:
            log.warning("录音结束：没有采到任何数据")
            self._set_state("idle")
            self.bridge.error.emit("未录制到音频")
            return

        # 时长按单声道样本数 / 采样率算（录音可能是立体声或非 16k）
        log.info("录音结束：通路=%s 采样率=%d 通道=%d 时长=%.2fs 峰值=%d 均值=%.1f "
                 "标准差=%.1f 谱质心=%.0fHz 判定=%s",
                 label, rate, ch, st["n"] / float(rate), st["peak"], st["mean"],
                 st["sd"], st.get("centroid", 0.0), classify_stats(st))

        # 用实测数据区分「通路死了」和「你真的没说话」。
        # 过去这两种都只弹"未检测到声音，请检查麦克风"，把用户引向了错误方向。
        if classify_stats(st) != "ok":
            self._set_state("idle")
            self.bridge.error.emit(
                f"麦克风通路异常：未收到任何信号"
                f"（峰值 {st['peak']}，标准差 {st['sd']:.0f}，通路 {label}）")
            return

        if not had_sound:
            self._set_state("idle")
            self.bridge.error.emit(
                f"未检测到有效语音（峰值 {st['peak']}，通路 {label}）")
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        audio_file = os.path.join(AUDIO_DIR, f"{timestamp}.wav")
        try:
            wf = wave.open(audio_file, 'wb')
            wf.setnchannels(ch)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(rate)
            wf.writeframes(b''.join(frames))
            wf.close()
        except Exception:
            log.error("写音频文件失败 %s", audio_file, exc_info=True)
            self._set_state("idle")
            self.bridge.error.emit("保存录音文件失败（详见日志）")
            return

        self._set_state("transcribing")

        # 非常驻模式下模型是和录音并行加载的，短录音可能还没装完，这里等它
        if not self.model_loaded:
            log.info("等待模型加载完成…")
            if not self._wait_model():
                self._set_state("idle")
                self.bridge.error.emit("模型没加载成功，本次无法转写（详见日志）")
                return

        text = ""
        try:
            t0 = time.time()
            segments, info = self.model.transcribe(audio_file)
            text = "".join(seg.text for seg in segments).strip()
            log.info("转写完成：耗时=%.1fs 字数=%d", time.time() - t0, len(text))
        except Exception as e:
            log.error("转写失败", exc_info=True)
            self.bridge.error.emit(f"转写失败：{e}（详见日志）")

        if text:
            try:
                pyperclip.copy(text)
            except Exception:
                log.warning("复制到剪贴板失败", exc_info=True)
            try:
                save_transcript(timestamp, text)
            except Exception:
                log.warning("保存转写文件失败", exc_info=True)
            self.bridge.transcribed.emit(text)
        else:
            self.bridge.transcribed.emit("")

        self._set_state("idle")

        # 这次用完了：开始倒计时，IDLE_UNLOAD_S 秒内没人再录就把模型和显存还回去。
        # 不立刻释放是为了让连着录几句时不必反复重载（每次约 3.5 秒）。
        self._schedule_idle_unload()


# ----------------------------------------------------------------------------
# 图标绘制（无文字，纯矢量）
# ----------------------------------------------------------------------------
def draw_mic(p, cx, cy, r, color):
    s = r * 1.05
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    head = QRectF(cx - s * 0.15, cy - s * 0.36, s * 0.30, s * 0.34)
    p.drawRoundedRect(head, s * 0.15, s * 0.15)
    pen = QPen(color, max(1.6, s * 0.07), Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    arc = QRectF(cx - s * 0.16, cy - s * 0.06, s * 0.32, s * 0.32)
    p.drawArc(arc, 180 * 16, 180 * 16)
    p.drawLine(QPointF(cx, cy + s * 0.10), QPointF(cx, cy + s * 0.24))
    p.drawLine(QPointF(cx - s * 0.12, cy + s * 0.24), QPointF(cx + s * 0.12, cy + s * 0.24))


def draw_wave(p, cx, cy, r, level, color):
    n = 5
    profile = [0.55, 0.85, 1.0, 0.85, 0.55]
    bar_w = r * 0.16
    gap = r * 0.10
    max_h = r * 0.95
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    for i in range(n):
        # 柱子高度完全由真实音量决定：说话→升高，静音→几乎贴底
        h = max_h * min(1.0, level * profile[i] * 1.7)
        h = max(h, r * 0.04)
        x = cx + (i - (n - 1) / 2.0) * (bar_w + gap)
        rect = QRectF(x - bar_w / 2.0, cy - h / 2.0, bar_w, h)
        p.drawRoundedRect(rect, bar_w / 2.0, bar_w / 2.0)


def draw_spinner(p, cx, cy, r, angle, color):
    pen = QPen(color, max(2.0, r * 0.18), Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    p.drawArc(rect, int(angle * 16) % (360 * 16), 260 * 16)


# ----------------------------------------------------------------------------
# 悬浮球窗口
# ----------------------------------------------------------------------------
class FloatingBall(QWidget):
    def __init__(self, bridge, controller, cfg):
        super().__init__()
        self.bridge = bridge
        self.controller = controller
        self.cfg = cfg

        # 初始状态问控制器要，不能硬编码 "loading"：控制器在悬浮球 connect 信号
        # 之前就可能已经发过状态了，那一下会丢，球就会永远转圈。
        self._state = controller.initial_ui_state()
        self._level = 0.0
        self._level_display = 0.0
        self._anim_t = 0.0
        self._angle = 0.0
        self._press_pos = None
        self._drag_start = None
        self._dragging = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(W, W)
        self.setCursor(Qt.PointingHandCursor)

        # 初始位置
        screen = QGuiApplication.primaryScreen().availableGeometry()
        pos = cfg.get("ball_pos")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            self.move(int(pos[0]), int(pos[1]))
        else:
            self.move(screen.right() - W - 40, screen.top() + screen.height() // 3)

        # 信号连接
        bridge.level.connect(self._on_level)
        bridge.state_changed.connect(self._on_state)
        bridge.model_ready.connect(self._on_model_ready)
        bridge.transcribed.connect(self._on_transcribed)
        bridge.error.connect(self._on_error)
        bridge.mic_info.connect(self._on_mic_info)

        self.toast = Toast(self)

        # 动画定时器
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        # 托盘图标
        self.tray = None
        self._setup_tray()

    # -- 信号回调 -----------------------------------------------------------
    def _on_level(self, v):
        self._level = max(0.0, min(1.0, float(v)))

    def _on_state(self, s):
        self._state = s
        if s == "recording":
            self._level = 0.0
            self._level_display = 0.0
        self.update()

    def _on_model_ready(self, device):
        self._on_state("idle")
        label = "GPU" if device == "cuda" else "CPU（较慢）"
        mic = self.controller.mic.chosen
        extra = f" · 麦克风 {mic.name}" if mic else ""
        self.toast.show_message(f"模型已就绪 · {label}{extra}", self)

    def _on_transcribed(self, text):
        if text:
            preview = text if len(text) <= 30 else text[:30] + "…"
            self.toast.show_message(f"已复制 ✓  {preview}", self)
        else:
            self.toast.show_message("未识别到语音", self)

    def _on_error(self, msg):
        log.warning("提示用户：%s", msg)
        self.toast.show_message(msg, self)

    def _on_mic_info(self, msg):
        self.toast.show_message(msg, self)

    # -- 动画 ---------------------------------------------------------------
    def _tick(self):
        self._anim_t += 0.033
        self._angle = (self._angle + 6) % 360
        # 只在录音时响应音量；低于噪声门限视为静音（柱子不动）
        if self._state != "recording":
            self._level = 0.0
        target = self._level if self._level >= NOISE_GATE else 0.0
        if target > self._level_display:
            self._level_display += (target - self._level_display) * 0.6
        else:
            self._level_display *= 0.72
        if self._level_display < 0.0005:
            self._level_display = 0.0
        self.update()

    # -- 绘制 ---------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        r = BALL_R
        t = self._anim_t

        # 阴影
        p.setPen(Qt.NoPen)
        sh = QRadialGradient(QPointF(cx, cy + 4), r * 1.35)
        sh.setColorAt(0, QColor(0, 0, 0, 90))
        sh.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(sh)
        p.drawEllipse(QRectF(cx - r * 1.35, cy + 4 - r * 1.35, r * 2.7, r * 2.7))

        state = self._state
        if state == "recording":
            accent = ACCENT_REC
        elif state == "transcribing":
            accent = ACCENT_WORK
        elif state == "loading":
            accent = QColor("#8a8fa8")
        else:
            accent = ACCENT_IDLE

        # 录音时的呼吸光环
        if state == "recording":
            pulse = 0.5 + 0.5 * math.sin(t * 4.0)
            ring_r = r + 3 + pulse * 3
            ring = QPen(QColor(255, 77, 94, int(120 * (1 - pulse * 0.5))), 2.5)
            p.setPen(ring)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2))

        # 球体
        body = QRadialGradient(QPointF(cx - r * 0.35, cy - r * 0.42), r * 1.7)
        body.setColorAt(0.0, QColor("#3c415f"))
        body.setColorAt(1.0, QColor("#171a2b"))
        p.setBrush(QBrush(body))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))

        # 待机时的内圈描边
        if state == "idle":
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 60), 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - r + 2, cy - r + 2, 2 * r - 4, 2 * r - 4))

        # 中心内容
        if state == "loading":
            draw_spinner(p, cx, cy, r * 0.42, self._angle, QColor("#cfd3e6"))
        elif state == "idle":
            draw_mic(p, cx, cy, r, FG)
        elif state == "recording":
            draw_wave(p, cx, cy, r, self._level_display, FG)
        elif state == "transcribing":
            draw_spinner(p, cx, cy, r * 0.42, self._angle, accent)

        p.end()

    # -- 交互：拖拽与点击 ---------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._drag_start = self.pos()
            self._dragging = False
        elif e.button() == Qt.RightButton:
            self._show_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._press_pos is not None and (e.buttons() & Qt.LeftButton):
            delta = e.globalPosition().toPoint() - self._press_pos
            if not self._dragging and delta.manhattanLength() > 6:
                self._dragging = True
            if self._dragging:
                self.move(self._drag_start + delta)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            was_drag = self._dragging
            self._dragging = False
            self._press_pos = None
            if not was_drag:
                self.controller.toggle()

    # -- 菜单 / 托盘 --------------------------------------------------------
    def _build_menu(self):
        menu = QMenu(self)
        act_folder = menu.addAction("打开转写文件夹")
        act_folder.triggered.connect(self._open_folder)

        mic_menu = menu.addMenu("选择麦克风")
        # 子菜单每次展开时才填充，这样设备列表是新的，而构建菜单本身不碰 PortAudio
        mic_menu.aboutToShow.connect(lambda m=mic_menu: self._populate_mic_menu(m))

        act_diag = menu.addAction("麦克风诊断")
        act_diag.triggered.connect(self._mic_diagnose)

        act_log = menu.addAction("打开日志")
        act_log.triggered.connect(self._open_log)

        menu.addSeparator()
        # 不设"常驻/非常驻"开关：语音识别按需启动、闲置自动释放，
        # 这里只留一个"现在就想关掉"的出口。
        if self.controller.model_loaded:
            act_close = menu.addAction("关闭语音识别（释放约 1.9GB 显存）")
            act_close.triggered.connect(self._close_asr)
        else:
            act_close = menu.addAction("语音识别未运行")
            act_close.setEnabled(False)

        menu.addSeparator()
        act_auto = menu.addAction("开机自启动")
        act_auto.setCheckable(True)
        act_auto.setChecked(is_autostart_enabled())
        act_auto.toggled.connect(self._toggle_autostart)
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self._quit)
        return menu

    def _populate_mic_menu(self, menu):
        """填充麦克风子菜单。

        关键：只用 snapshot_paths() 读已缓存的设备快照，绝不在 GUI 线程初始化
        PortAudio —— 那会和后台探测线程争 Pa_Initialize 直接把进程打崩。
        """
        menu.clear()
        mic = self.controller.mic
        override = self.cfg.get("mic_device")
        manual = isinstance(override, dict) and bool(override.get("device"))

        act_auto = menu.addAction("自动（推荐）")
        act_auto.setCheckable(True)
        act_auto.setChecked(not manual)
        act_auto.triggered.connect(lambda: self._set_mic(None))
        menu.addSeparator()

        paths = mic.snapshot_paths()
        if not paths:
            act = menu.addAction("（正在探测设备…）")
            act.setEnabled(False)
            return

        current = mic.chosen
        for p in paths:
            label = f"{p.name}  [{p.host_api_name}]"
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(bool(manual and override.get("host_api") == p.host_api_name
                                and override.get("device") == p.name))
            act.triggered.connect(
                lambda _=False, p=p: self._set_mic(
                    {"host_api": p.host_api_name, "device": p.name}))
            if current is not None and current.key() == p.key():
                act.setText(label + "   ← 当前")

        menu.addSeparator()
        act_scan = menu.addAction("重新扫描设备")
        act_scan.triggered.connect(self._rescan_mics)

    def _rescan_mics(self):
        self.toast.show_message("正在重新扫描麦克风…", self)
        self.controller.mic.refresh_async()

    def _set_mic(self, override):
        self.cfg["mic_device"] = override
        save_config(self.cfg)
        mic = self.controller.mic
        mic.bad.clear()
        if override is None:
            log.info("切换为自动选择麦克风")
            self.toast.show_message("已切回自动选择麦克风", self)
        else:
            log.info("手动指定麦克风：%s @ %s", override.get("device"), override.get("host_api"))
            self.toast.show_message(f"已指定：{override.get('device')}", self)
        threading.Thread(target=self._reprobe_mic, daemon=True).start()

    def _reprobe_mic(self):
        mic = self.controller.mic
        try:
            path = mic.resolve()
        except Exception:
            log.error("重新探测麦克风异常", exc_info=True)
            path = None
        if path is None:
            self.bridge.mic_info.emit("新的麦克风不可用，已自动回退（详见日志）")
        else:
            self.bridge.mic_info.emit(f"当前麦克风：{path.name}")

    def _mic_diagnose(self):
        self.toast.show_message("正在诊断麦克风…", self)
        threading.Thread(target=self._reprobe_mic, daemon=True).start()

    def _show_menu(self, pos):
        self._build_menu().exec(pos)

    def _open_folder(self):
        os.startfile(TRANSCRIPT_DIR)

    def _open_log(self):
        try:
            os.startfile(LOG_DIR)
        except Exception:
            log.warning("打开日志目录失败", exc_info=True)

    def _toggle_autostart(self, enabled):
        if set_autostart(enabled):
            self.toast.show_message("已开启开机自启动" if enabled else "已关闭开机自启动", self)
        else:
            self.toast.show_message("设置失败（无权限）", self)

    def _close_asr(self):
        """手动关闭语音识别，立刻把显存还回去。"""
        self.toast.show_message("正在关闭语音识别…", self)
        threading.Thread(target=self._close_asr_bg, daemon=True).start()

    def _close_asr_bg(self):
        try:
            if self.controller.unload_now():
                self.bridge.mic_info.emit("语音识别已关闭，显存已释放")
            else:
                self.bridge.mic_info.emit("语音识别本来就没在运行")
        except Exception:
            log.error("关闭语音识别失败", exc_info=True)
            self.bridge.mic_info.emit("关闭失败（详见日志）")

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self._make_icon(), self)
        self.tray.setToolTip("语音悬浮球")
        self.tray.setContextMenu(self._build_menu())
        self.tray.show()

    def _make_icon(self):
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT_IDLE)
        p.drawEllipse(2, 2, size - 4, size - 4)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(size * 0.3, size * 0.3, size * 0.4, size * 0.4)
        p.end()
        return QIcon(pm)

    def _on_second_launch(self):
        """第二次启动被拦截时，把已有悬浮球拉到前台，让用户看到"它还在"。"""
        self.show()
        self.raise_()
        self.toast.show_message("已在运行", self)

    def _quit(self):
        log.info("用户请求退出")
        self.controller.shutdown()
        self.cfg["ball_pos"] = [self.x(), self.y()]
        save_config(self.cfg)
        server = getattr(self, "server", None)
        if server is not None:
            server.release()
        QApplication.quit()


# ----------------------------------------------------------------------------
# 短暂提示小窗
# ----------------------------------------------------------------------------
class Toast(QWidget):
    def __init__(self, ball):
        super().__init__()
        self._ball = ball
        self._text = ""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(300)

    def show_message(self, text, ball=None):
        self._text = text
        self._hide_timer.stop()
        self._anim.stop()
        self.setWindowOpacity(1.0)
        self.adjustSize()
        g = (ball or self._ball).geometry()
        x = g.center().x() - self.width() // 2
        y = g.top() - self.height() - 12
        self.move(x, max(0, y))
        self.show()
        self.raise_()
        self._hide_timer.start(2400)

    def _fade_out(self):
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide)
        self._anim.start()

    def sizeHint(self):
        f = QFont()
        f.setPointSize(10)
        fm = QFontMetrics(f)
        w = min(fm.horizontalAdvance(self._text) + 40, 460)
        return QSize(w, 40)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 32, 46, 235))
        p.drawRoundedRect(QRectF(r), 12, 12)
        p.setPen(QColor("#ffffff"))
        f = QFont()
        f.setPointSize(10)
        p.setFont(f)
        p.drawText(QRectF(r).adjusted(16, 6, -16, -6), Qt.AlignVCenter | Qt.AlignLeft, self._text)
        p.end()


# ----------------------------------------------------------------------------
# 全局快捷键 & 开机自启动
# ----------------------------------------------------------------------------
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "VoiceBall"
_hotkey_listener = None  # 保持引用，防止监听器被回收


def normalize_hotkey(hotkey):
    """把 'ctrl+alt+space' 规范成 '<ctrl>+<alt>+<space>'。"""
    hotkey = (hotkey or "").strip()
    if not hotkey:
        return "<ctrl>+<alt>+<space>"
    if "<" not in hotkey:
        parts = hotkey.split("+")
        # 单个字符是普通键，多字符是特殊键名（ctrl/alt/space/f5 等）需加 <>
        parts = [f"<{p.strip()}>" if len(p.strip()) > 1 else p.strip() for p in parts]
        hotkey = "+".join(parts)
    return hotkey


def start_hotkey(bridge, hotkey):
    """注册全局快捷键切换录音（默认 Ctrl+Alt+Space）。

    注意：pynput 的监听器跑在自己的线程里，绝不能在那里直接改控制器状态。
    这里只发一个信号，由 Qt 派发回 GUI 线程执行，避免跨线程状态竞争。
    """
    global _hotkey_listener
    try:
        from pynput import keyboard
        _hotkey_listener = keyboard.GlobalHotKeys(
            {hotkey: lambda: bridge.toggle_requested.emit()})
        _hotkey_listener.start()
        log.info("全局快捷键已注册：%s", hotkey)
    except Exception as e:
        # 以前这里只 print()，而 pythonw 下 stdout 是丢弃的，失败完全无声
        log.error("快捷键注册失败：%s", e, exc_info=True)


def _autostart_command():
    pyw = os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe")
    script = os.path.join(BASE_DIR, "voice_ball.py")
    return f'"{pyw}" "{script}"'


def is_autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
        return True
    except OSError:
        return False


def set_autostart(enable):
    try:
        if enable:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as k:
                try:
                    winreg.DeleteValue(k, AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------------
# 单实例保护
#
# 没有它的时候：开机自启动 + 手动点 bat 会叠出两个悬浮球 —— 两份 CUDA 上下文、
# 两个全局热键监听、两份 1.5GB 模型。用户看到的就是"桌面上启动了两个"。
# ----------------------------------------------------------------------------
SINGLE_INSTANCE_KEY = "VoiceBall_SingleInstance"


def _notify_existing_instance():
    """若已有实例在跑，通知它现身并返回 True（本进程应当直接退出）。"""
    sock = QLocalSocket()
    sock.connectToServer(SINGLE_INSTANCE_KEY)
    if not sock.waitForConnected(300):
        return False
    try:
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
    except Exception:
        log.warning("通知已有实例失败", exc_info=True)
    sock.disconnectFromServer()
    return True


class SingleInstanceServer(QObject):
    """持有单实例锁；第二次启动时把已有悬浮球拉到前台。"""

    activated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = None
        self._handled = set()

    def listen(self):
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)  # 清理上次异常退出留下的陈旧管道
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_connection)
        if not self.server.listen(SINGLE_INSTANCE_KEY):
            log.error("单实例监听失败：%s（将以多实例方式运行）",
                      self.server.errorString())
            return False
        log.info("已持有单实例锁")
        return True

    def release(self):
        if self.server is None:
            return
        try:
            self.server.close()
            QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        except Exception:
            log.warning("释放单实例锁失败", exc_info=True)

    def _on_connection(self):
        conn = self.server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda c=conn: self._on_read(c))
        conn.disconnected.connect(conn.deleteLater)
        if conn.bytesAvailable() > 0:
            self._on_read(conn)

    def _on_read(self, conn):
        key = id(conn)
        if key in self._handled:
            return
        self._handled.add(key)
        try:
            data = bytes(conn.readAll())
        except Exception:
            data = b""
        log.info("收到第二次启动请求：%r", data)
        self.activated.emit()


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------
def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    log.info("=" * 64)
    log.info("语音悬浮球启动 (PID %d)", os.getpid())

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 单实例判定必须在建窗口、加载模型之前 —— 否则第二个实例白加载 1.5GB 模型
    if _notify_existing_instance():
        log.info("已有实例在运行，本次启动直接退出")
        return

    server = SingleInstanceServer()
    server.listen()

    cfg = load_config()
    log.info("配置：%s", {k: v for k, v in cfg.items() if k != "ball_pos"})
    bridge = Bridge()
    controller = Controller(bridge, cfg)
    ball = FloatingBall(bridge, controller, cfg)
    ball.server = server
    server.activated.connect(ball._on_second_launch)
    ball.show()
    QTimer.singleShot(100, lambda: ball.toast.show_message("正在加载模型…", ball))

    # 全局快捷键经 Bridge 派发回 GUI 线程，避免跨线程改状态
    bridge.toggle_requested.connect(controller.toggle)
    start_hotkey(bridge, normalize_hotkey(cfg.get("hotkey", "")))

    try:
        sys.exit(app.exec())
    finally:
        controller.shutdown()


if __name__ == "__main__":
    main()
