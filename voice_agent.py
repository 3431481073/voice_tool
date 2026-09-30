import os
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import sys
import json
import time
import glob
import queue
import threading
import site

import pyperclip
import pyaudio
import wave
from pynput import keyboard

def setup_cuda_path():
    added = []
    for sp in site.getsitepackages():
        for d in glob.glob(os.path.join(sp, 'nvidia*')):
            if os.path.isdir(d):
                for root, subdirs, files in os.walk(d):
                    if 'bin' in subdirs:
                        bin_dir = os.path.join(root, 'bin')
                        if os.path.isdir(bin_dir) and bin_dir not in added:
                            os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
                            added.append(bin_dir)
    return added

setup_cuda_path()

from faster_whisper import WhisperModel

CONFIG_FILE = "config.json"

def load_config():
    default_config = {
        "whisper_model": "small",
        "hotkey": "<ctrl>+<alt>+<space>"
    }
    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        # 确保 hotkey 格式正确
        hotkey = config.get("hotkey", default_config["hotkey"])
        if "<" not in hotkey:
            # 自动转换 ctrl+alt+space -> <ctrl>+<alt>+<space>
            parts = hotkey.split("+")
            parts = [f"<{p}>" if p.lower() in ["ctrl", "alt", "shift"] else p for p in parts]
            hotkey = "+".join(parts)
        config["hotkey"] = hotkey
        return config
    except:
        return default_config

config = load_config()
WHISPER_MODEL = config.get("whisper_model", "small")
HOTKEY = config.get("hotkey", "<ctrl>+<alt>+<space>")

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
AUDIO_DIR = "audio_temp"
TRANSCRIPT_DIR = "transcripts"

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

recording = False
recording_start_time = None
frames = []
state_queue = queue.Queue()

print("正在加载 Whisper 模型...")
model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
print("模型加载完成，使用 GPU")

def start_recording():
    global recording, recording_start_time, frames
    if recording:
        return
    recording = True
    recording_start_time = time.time()
    frames = []
    state_queue.put("listening")
    print("开始录音...")

    def record_loop():
        pa = pyaudio.PyAudio()
        stream = pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                         input=True, frames_per_buffer=CHUNK)
        while recording:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
            except:
                break
        stream.stop_stream()
        stream.close()
        pa.terminate()

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        audio_file = os.path.join(AUDIO_DIR, f"{timestamp}.wav")
        wf = wave.open(audio_file, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pa.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()

        state_queue.put("transcribing")
        print("正在转写...")
        try:
            segments, info = model.transcribe(audio_file)
            text = "".join(seg.text for seg in segments).strip()
        except Exception as e:
            text = f"[转写失败: {e}]"

        if text:
            pyperclip.copy(text)
            print(f"已复制到剪贴板：{text}")

        save_transcript(timestamp, text)
        state_queue.put("idle")
        print("完成。")

    threading.Thread(target=record_loop, daemon=True).start()

def stop_recording():
    global recording
    if recording:
        recording = False
        print("停止录音。")

def save_transcript(timestamp, text):
    filepath = os.path.join(TRANSCRIPT_DIR, f"{timestamp}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

def toggle_recording():
    global recording
    if recording:
        stop_recording()
    else:
        start_recording()

def on_activate():
    toggle_recording()

def main():
    print(f"语音工具已启动。按 {HOTKEY} 开始/停止录音。")
    try:
        with keyboard.GlobalHotKeys({HOTKEY: on_activate}) as h:
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n退出。")
    except Exception as e:
        print(f"运行异常：{e}")

if __name__ == "__main__":
    main()