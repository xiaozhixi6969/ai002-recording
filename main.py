# -*- coding: utf-8 -*-
"""
Ai002-工具流-手机录音-智能解析
主程序入口 - Android 端录音+文本双轨独立 AI 解析推送应用
作者：AI喜小二 for 萧先生
版本：v1.1.0  日期：2026-04-02

双轨架构：
  录音轨：扫描录音文件 → DeepSeek AI（基于文件名/大小/时间推断） → 企微推送
  文本轨：扫描转写文本 → DeepSeek AI（深度分析文本内容） → 企微推送
  两条轨完全独立，互不依赖，各自触发各自推送
"""

import os
import sys
import json
import time
import threading
import hashlib
from datetime import datetime

# ─────────────────────────────────────────────
# Kivy 配置（必须在 import kivy 之前设置）
# ─────────────────────────────────────────────
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.utils import platform
from kivy.core.window import Window
from kivy.metrics import dp

# ─────────────────────────────────────────────
# 配置常量
# ─────────────────────────────────────────────
APP_NAME = "Ai002录音智能解析"
APP_VERSION = "v1.1.0"

DEEPSEEK_API_KEY = "sk-95f06179faca4aa2994c11f834d5f4f1"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=a8849277-0088-493b-b41d-b34ddcf668a1"

# 录音格式
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".amr", ".opus", ".ogg", ".wma", ".3gp", ".ogg"}
# 文本格式
TEXT_EXTENSIONS = {".txt", ".json", ".srt", ".docx", ".md"}

# 安卓扫描目录
SCAN_DIRS = [
    "/sdcard/Recordings",
    "/sdcard/MIUI/sound_recorder",
    "/sdcard/Sound Recorder",
    "/sdcard/MIUI/recorder",
    "/sdcard/Recorder",
    "/sdcard/Voice Recorder",
    "/sdcard/Music",
    "/sdcard/Download",
    "/sdcard/DCIM",
    "/sdcard/",
    "/storage/emulated/0/Recordings",
    "/storage/emulated/0/MIUI/sound_recorder",
    "/storage/emulated/0/MIUI/recorder",
    "/storage/emulated/0/Sound Recorder",
    "/storage/emulated/0/Voice Recorder",
    "/storage/emulated/0/Music",
    "/storage/emulated/0/Download",
    "/storage/emulated/0/Documents",
    "/storage/emulated/0/",
]

# 数据存储路径
DATA_DIR = os.path.join(os.path.expanduser("~"), ".ai002_data")
PROCESSED_DB = os.path.join(DATA_DIR, "processed_files.json")
LOG_FILE = os.path.join(DATA_DIR, "app.log")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_processed_db():
    ensure_data_dir()
    if os.path.exists(PROCESSED_DB):
        try:
            with open(PROCESSED_DB, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_processed_db(db):
    ensure_data_dir()
    with open(PROCESSED_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def load_config():
    ensure_data_dir()
    default_config = {
        "deepseek_api_key": DEEPSEEK_API_KEY,
        "webhook_url": WEBHOOK_URL,
        "scan_interval": 30,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                default_config.update(cfg)
        except Exception:
            pass
    return default_config


def save_config(cfg):
    ensure_data_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def log(msg):
    ensure_data_dir()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def file_hash(filepath):
    try:
        stat = os.stat(filepath)
        key = f"{filepath}_{stat.st_size}_{int(stat.st_mtime)}"
        return hashlib.md5(key.encode()).hexdigest()
    except Exception:
        return None


def get_scan_dirs():
    dirs = list(SCAN_DIRS)
    return [d for d in dirs if os.path.exists(d)]


def get_file_age_days(filepath):
    """获取文件年龄（天）"""
    try:
        stat = os.stat(filepath)
        age_seconds = time.time() - stat.st_mtime
        return age_seconds / 86400
    except Exception:
        return 0


# ─────────────────────────────────────────────
# 文本文件读取
# ─────────────────────────────────────────────

def read_text_content(path):
    """读取文本文件内容"""
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get("text", data.get("transcript", data.get("content", str(data))))
            return str(data)
        elif ext == ".srt":
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            text_lines = []
            for line in lines:
                line = line.strip()
                if line.isdigit():
                    continue
                if "-->" in line:
                    continue
                if line:
                    text_lines.append(line)
            return " ".join(text_lines)
        elif ext == ".docx":
            try:
                import zipfile
                from xml.etree import ElementTree as ET
                with zipfile.ZipFile(path, "r") as z:
                    xml = z.read("word/document.xml")
                tree = ET.fromstring(xml)
                texts = [t.text for t in tree.iter(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                ) if t.text]
                return " ".join(texts)
            except Exception:
                return ""
        else:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        log(f"读取文本失败 {path}: {e}")
        return ""


# ─────────────────────────────────────────────
# 文件扫描
# ─────────────────────────────────────────────

def scan_all_files(processed_db):
    """扫描所有录音文件和文本文件"""
    new_audio = []
    new_text = []
    scan_dirs = get_scan_dirs()

    for scan_dir in scan_dirs:
        try:
            for root, dirs, files in os.walk(scan_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    fpath = os.path.join(root, fname)
                    fhash = file_hash(fpath)
                    if not fhash:
                        continue
                    if fhash in processed_db:
                        continue
                    # 录音文件
                    if ext in AUDIO_EXTENSIONS:
                        new_audio.append(fpath)
                    # 文本文件
                    elif ext in TEXT_EXTENSIONS:
                        new_text.append(fpath)
        except PermissionError:
            pass
        except Exception as e:
            log(f"扫描异常 {scan_dir}: {e}")

    return new_audio, new_text


# ─────────────────────────────────────────────
# DeepSeek API
# ─────────────────────────────────────────────

def call_deepseek(prompt, api_key):
    import urllib.request
    import urllib.error

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是萧先生的智能录音助理，专注于投资、商务录音的智能摘要分析。输出简洁、准确、有商业价值。"
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 800
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        req = urllib.request.Request(DEEPSEEK_API_URL, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        log(f"DeepSeek HTTP错误 {e.code}: {err_body}")
        return None
    except Exception as e:
        log(f"DeepSeek 调用异常: {e}")
        return None


# ─────────────────────────────────────────────
# 企微推送
# ─────────────────────────────────────────────

def push_to_wecom(text, webhook_url):
    import urllib.request
    import urllib.error

    if len(text) > 4000:
        text = text[:3950] + "\n\n...（内容过长已截断）"

    payload = {
        "msgtype": "text",
        "text": {"content": text}
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}

    try:
        req = urllib.request.Request(webhook_url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("errcode") == 0:
                return True
            log(f"企微推送失败: {result}")
            return False
    except Exception as e:
        log(f"企微推送异常: {e}")
        return False


# ─────────────────────────────────────────────
# 录音轨处理（Track A）
# ─────────────────────────────────────────────

def build_audio_prompt(filename, filepath):
    """构建录音文件 AI 解析 Prompt（无转写文本时基于元数据推断）"""
    try:
        size_bytes = os.path.getsize(filepath)
        size_mb = size_bytes / (1024 * 1024)
        stat = os.stat(filepath)
        mtime_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        size_mb = 0
        mtime_str = "未知"

    # 尝试从文件名提取关键信息
    name_no_ext = os.path.splitext(filename)[0]
    # 过滤掉日期格式和序号，保留业务关键词
    import re
    # 去除常见日期格式
    clean_name = re.sub(r'[\d_年月日时分秒\-]+', ' ', name_no_ext)
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    business_keywords = clean_name if clean_name else name_no_ext

    prompt = f"""你是萧先生的智能录音助理，请对以下录音文件进行 AI 智能解析。

【录音文件信息】
- 文件名：{filename}
- 文件大小：{size_mb:.2f} MB
- 创建时间：{mtime_str}
- 关键词（文件名推断）：{business_keywords}

请根据以上信息，结合萧先生作为投资/金融专业人士的背景，对录音内容进行合理推断和分析。

请按以下纯文本格式输出（适合企业微信显示，不用 Markdown）：

🎙️ 录音智能解析 | {filename}
📅 {datetime.now().strftime("%Y-%m-%d %H:%M")}
📁 {filename}（{size_mb:.2f}MB）

【内容推断】
（基于文件名和文件信息，对录音内容进行合理推断，3-5句话）

【关键信息点】
（基于文件名中的业务关键词，推断可能的讨论议题，列出2-4个要点）

【建议跟进】
▸ （基于推断内容，给出合理的跟进建议或待确认事项）

【风险提示】
▸ （标注任何需要关注的风险点或待核实信息，无则写"无明显风险提示"）

字数控制在300字以内，语言简洁精准，符合投资/商务专业人士的工作场景。"""

    return prompt


def process_audio_file(audio_path, config, status_cb=None):
    """处理单个录音文件（录音轨）"""
    filename = os.path.basename(audio_path)

    def status(msg):
        log(msg)
        if status_cb:
            status_cb(msg)

    status(f"🎙️ [录音轨] 开始处理：{filename}")

    try:
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    except Exception:
        size_mb = 0

    status(f"  🤖 [录音轨] 调用 DeepSeek AI 解析...")
    prompt = build_audio_prompt(filename, audio_path)
    api_key = config.get("deepseek_api_key", DEEPSEEK_API_KEY)
    summary = call_deepseek(prompt, api_key)

    if not summary:
        status(f"  ❌ [录音轨] DeepSeek 调用失败")
        return False

    status(f"  ✅ [录音轨] AI 解析成功（{len(summary)} 字）")

    # 组装推送消息
    header = (
        f"🎙️ Ai002 录音智能解析\n"
        f"{'─' * 28}\n"
        f"📁 {filename}\n"
        f"📦 {size_mb:.2f} MB\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'─' * 28}\n\n"
    )
    full_msg = header + summary

    status(f"  📤 [录音轨] 推送到企业微信...")
    webhook_url = config.get("webhook_url", WEBHOOK_URL)
    ok = push_to_wecom(full_msg, webhook_url)

    if ok:
        status(f"  ✅ [录音轨] 推送成功！")
    else:
        status(f"  ❌ [录音轨] 推送失败")
    return ok


# ─────────────────────────────────────────────
# 文本轨处理（Track B）
# ─────────────────────────────────────────────

def build_text_prompt(filename, text_content):
    """构建转写文本 AI 深度解析 Prompt"""
    # 截断超长文本
    truncated = text_content[:8000] if len(text_content) > 8000 else text_content

    prompt = f"""你是萧先生的智能录音助理，请对以下录音转写文本进行深度智能分析。

【文本文件信息】
- 文件名：{filename}
- 字符数：{len(text_content)} 字
- 分析时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}

【转写文本内容】
{truncated}

请按以下纯文本格式输出深度分析结果（适合企业微信显示，不用 Markdown）：

📄 Ai002 转写文本解析 | {filename}
📅 {datetime.now().strftime("%Y-%m-%d %H:%M")}
📁 {filename}（{len(text_content)} 字）

【核心内容】
（3-5句话概括文本的主要内容，准确反映说话者意图和讨论焦点）

【关键信息点】
① （第一个关键信息或重要决定）
② （第二个关键信息或数据点）
③ （第三个关键信息或待办事项，如有）
④ （如有第四点）

【行动建议】
▸ （基于文本内容，给出明确的跟进建议、决策选项或下一步行动）

【风险提示】
▸ （识别潜在风险、不一致之处或需要特别关注的事项，无则写"无"）

字数控制在350字以内，语言简洁精准，符合投资/商务专业人士的工作场景。"""

    return prompt


def process_text_file(text_path, config, status_cb=None):
    """处理单个转写文本文件（文本轨）"""
    filename = os.path.basename(text_path)

    def status(msg):
        log(msg)
        if status_cb:
            status_cb(msg)

    status(f"📄 [文本轨] 开始处理：{filename}")

    # 读取文本内容
    text_content = read_text_content(text_path)
    if not text_content or len(text_content.strip()) < 5:
        status(f"  ⚠️ [文本轨] 文本内容为空，跳过")
        return False

    status(f"  ✅ [文本轨] 读取文本成功（{len(text_content)} 字）")
    status(f"  🤖 [文本轨] 调用 DeepSeek AI 深度解析...")

    prompt = build_text_prompt(filename, text_content)
    api_key = config.get("deepseek_api_key", DEEPSEEK_API_KEY)
    summary = call_deepseek(prompt, api_key)

    if not summary:
        status(f"  ❌ [文本轨] DeepSeek 调用失败")
        return False

    status(f"  ✅ [文本轨] AI 解析成功（{len(summary)} 字）")

    # 组装推送消息
    header = (
        f"📄 Ai002 转写文本解析\n"
        f"{'─' * 28}\n"
        f"📁 {filename}\n"
        f"📝 {len(text_content)} 字\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'─' * 28}\n\n"
    )
    full_msg = header + summary

    status(f"  📤 [文本轨] 推送到企业微信...")
    webhook_url = config.get("webhook_url", WEBHOOK_URL)
    ok = push_to_wecom(full_msg, webhook_url)

    if ok:
        status(f"  ✅ [文本轨] 推送成功！")
    else:
        status(f"  ❌ [文本轨] 推送失败")
    return ok


# ─────────────────────────────────────────────
# 文件监听服务
# ─────────────────────────────────────────────

class FileWatcherService:
    """
    后台文件监听服务（双轨独立触发）
    - 录音轨：发现新录音文件 → AI 解析 → 推送
    - 文本轨：发现新转写文本 → AI 深度解析 → 推送
    """

    def __init__(self, status_callback=None):
        self.running = False
        self.thread = None
        self.status_callback = status_callback
        self.processed_db = load_processed_db()
        self.check_interval = 30
        self.stats = {
            "total_audio_processed": 0,
            "total_text_processed": 0,
            "total_audio_pushed": 0,
            "total_text_pushed": 0,
            "last_scan_time": None,
            "last_audio": None,
            "last_text": None,
        }

    def set_status(self, msg):
        log(msg)
        if self.status_callback:
            Clock.schedule_once(lambda dt: self.status_callback(msg), 0)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
        self.set_status("🟢 Ai002 双轨监听服务已启动")

    def stop(self):
        self.running = False
        self.set_status("🔴 监听服务已停止")

    def _watch_loop(self):
        self.set_status("🔍 启动全量扫描...")
        new_audio, new_text = scan_all_files(self.processed_db)

        # 首次启动：标记所有已知文件，不重复推送
        if new_audio or new_text:
            marked = 0
            for fpath in new_audio + new_text:
                fhash = file_hash(fpath)
                if fhash:
                    self.processed_db[fhash] = {
                        "path": fpath,
                        "type": "audio" if os.path.splitext(fpath)[1].lower() in AUDIO_EXTENSIONS else "text",
                        "marked_time": datetime.now().isoformat(),
                        "status": "skipped_initial"
                    }
                    marked += 1
            save_processed_db(self.processed_db)
            self.set_status(f"📋 首次扫描：标记 {marked} 个历史文件（不推送，避免刷屏）")
        else:
            self.set_status("📭 未发现录音或文本文件，等待新文件...")

        self.stats["last_scan_time"] = datetime.now().strftime("%H:%M:%S")

        while self.running:
            time.sleep(self.check_interval)
            if not self.running:
                break

            self.stats["last_scan_time"] = datetime.now().strftime("%H:%M:%S")
            config = load_config()
            new_audio, new_text = scan_all_files(self.processed_db)

            if not new_audio and not new_text:
                self.set_status(f"⏱ {self.stats['last_scan_time']} 扫描完成，暂无新文件")
                continue

            # ── 录音轨处理 ──
            if new_audio:
                self.set_status(f"🎙️ 发现 {len(new_audio)} 个新录音文件")
                for fpath in new_audio:
                    if not self.running:
                        break
                    fhash = file_hash(fpath)
                    if not fhash:
                        continue
                    ok = process_audio_file(fpath, config, self.set_status)
                    self.stats["total_audio_processed"] += 1
                    if ok:
                        self.stats["total_audio_pushed"] += 1
                    self.stats["last_audio"] = os.path.basename(fpath)
                    self.processed_db[fhash] = {
                        "path": fpath,
                        "type": "audio",
                        "processed_time": datetime.now().isoformat(),
                        "status": "pushed" if ok else "failed"
                    }
                    save_processed_db(self.processed_db)
                    time.sleep(3)

            # ── 文本轨处理 ──
            if new_text:
                self.set_status(f"📄 发现 {len(new_text)} 个新文本文件")
                for fpath in new_text:
                    if not self.running:
                        break
                    fhash = file_hash(fpath)
                    if not fhash:
                        continue
                    ok = process_text_file(fpath, config, self.set_status)
                    self.stats["total_text_processed"] += 1
                    if ok:
                        self.stats["total_text_pushed"] += 1
                    self.stats["last_text"] = os.path.basename(fpath)
                    self.processed_db[fhash] = {
                        "path": fpath,
                        "type": "text",
                        "processed_time": datetime.now().isoformat(),
                        "status": "pushed" if ok else "failed"
                    }
                    save_processed_db(self.processed_db)
                    time.sleep(3)


# ─────────────────────────────────────────────
# UI 界面
# ─────────────────────────────────────────────

class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.padding = dp(10)
        self.spacing = dp(8)
        self._build_ui()

    def _build_ui(self):
        Window.clearcolor = (0.07, 0.07, 0.10, 1)

        # 标题栏
        title_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56))
        title_label = Label(
            text="[b]Ai002 录音智能解析[/b]",
            markup=True,
            font_size=dp(18),
            color=(0.2, 0.8, 1, 1),
            halign="left", valign="middle",
        )
        title_label.bind(size=title_label.setter("text_size"))
        version_label = Label(
            text=f"v1.1.0",
            font_size=dp(12),
            color=(0.5, 0.5, 0.5, 1),
            size_hint_x=None, width=dp(60),
        )
        title_bar.add_widget(title_label)
        title_bar.add_widget(version_label)
        self.add_widget(title_bar)

        # 双轨状态卡片
        status_card = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(100),
            padding=dp(10), spacing=dp(4),
        )
        self.status_dot = Label(
            text="⚫ 服务未启动",
            font_size=dp(15), color=(0.9, 0.9, 0.9, 1),
            halign="left", valign="middle",
        )
        self.status_dot.bind(size=self.status_dot.setter("text_size"))

        self.stats_audio = Label(
            text="🎙️ 录音轨 | 已处理: 0 | 已推送: 0",
            font_size=dp(12), color=(0.5, 0.8, 1.0, 1),
            halign="left", valign="middle",
        )
        self.stats_audio.bind(size=self.stats_audio.setter("text_size"))

        self.stats_text = Label(
            text="📄 文本轨 | 已处理: 0 | 已推送: 0",
            font_size=dp(12), color=(0.5, 1.0, 0.7, 1),
            halign="left", valign="middle",
        )
        self.stats_text.bind(size=self.stats_text.setter("text_size"))

        self.last_scan = Label(
            text="上次扫描: --",
            font_size=dp(11), color=(0.5, 0.5, 0.5, 1),
            halign="left", valign="middle",
        )
        self.last_scan.bind(size=self.last_scan.setter("text_size"))

        status_card.add_widget(self.status_dot)
        status_card.add_widget(self.stats_audio)
        status_card.add_widget(self.stats_text)
        status_card.add_widget(self.last_scan)
        self.add_widget(status_card)

        # 按钮行
        btn_row = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(50), spacing=dp(8)
        )
        self.start_btn = Button(
            text="▶ 启动监听", font_size=dp(15),
            background_color=(0.1, 0.6, 0.3, 1), background_normal="",
        )
        self.start_btn.bind(on_press=self.on_start)

        self.stop_btn = Button(
            text="■ 停止", font_size=dp(15),
            background_color=(0.6, 0.1, 0.1, 1), background_normal="",
            disabled=True,
        )
        self.stop_btn.bind(on_press=self.on_stop)

        self.scan_btn = Button(
            text="🔍 立即扫描", font_size=dp(15),
            background_color=(0.2, 0.3, 0.7, 1), background_normal="",
        )
        self.scan_btn.bind(on_press=self.on_scan_now)

        btn_row.add_widget(self.start_btn)
        btn_row.add_widget(self.stop_btn)
        btn_row.add_widget(self.scan_btn)
        self.add_widget(btn_row)

        # 设置行
        settings_row = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8)
        )
        cfg_btn = Button(
            text="⚙ 配置", font_size=dp(14),
            background_color=(0.3, 0.3, 0.3, 1), background_normal="",
        )
        cfg_btn.bind(on_press=self.on_settings)

        clear_btn = Button(
            text="🗑 清除日志", font_size=dp(14),
            background_color=(0.3, 0.3, 0.3, 1), background_normal="",
        )
        clear_btn.bind(on_press=self.on_clear_log)

        settings_row.add_widget(cfg_btn)
        settings_row.add_widget(clear_btn)
        self.add_widget(settings_row)

        # 日志区域
        log_header = Label(
            text="运行日志", font_size=dp(13), color=(0.5, 0.5, 0.5, 1),
            size_hint_y=None, height=dp(24),
            halign="left", valign="middle",
        )
        log_header.bind(size=log_header.setter("text_size"))
        self.add_widget(log_header)

        scroll = ScrollView()
        self.log_text = Label(
            text="等待启动...\n",
            font_size=dp(12), color=(0.8, 0.8, 0.8, 1),
            halign="left", valign="top",
            size_hint_y=None,
        )
        self.log_text.bind(
            texture_size=lambda inst, val: setattr(inst, "height", val[1])
        )
        self.log_text.bind(size=self.log_text.setter("text_size"))
        scroll.add_widget(self.log_text)
        self.add_widget(scroll)

        self.watcher = FileWatcherService(status_callback=self._on_status_update)
        Clock.schedule_interval(self._refresh_stats, 5)

    def _on_status_update(self, msg):
        current = self.log_text.text
        lines = current.strip().split("\n")
        if len(lines) > 100:
            lines = lines[-100:]
        lines.append(msg)
        self.log_text.text = "\n".join(lines) + "\n"

    def _refresh_stats(self, dt):
        if self.watcher.running:
            self.status_dot.text = "🟢 双轨监听服务运行中"
            self.status_dot.color = (0.2, 1, 0.2, 1)
        else:
            self.status_dot.text = "⚫ 服务未启动"
            self.status_dot.color = (0.6, 0.6, 0.6, 1)

        s = self.watcher.stats
        self.stats_audio.text = (
            f"🎙️ 录音轨 | 已处理: {s['total_audio_processed']} | 已推送: {s['total_audio_pushed']}"
        )
        self.stats_text.text = (
            f"📄 文本轨 | 已处理: {s['total_text_processed']} | 已推送: {s['total_text_pushed']}"
        )
        self.last_scan.text = f"上次扫描: {s['last_scan_time'] or '--'}"

    def on_start(self, instance):
        self.watcher.start()
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self._on_status_update("▶ 双轨监听服务已启动")

    def on_stop(self, instance):
        self.watcher.stop()
        self.start_btn.disabled = False
        self.stop_btn.disabled = True

    def on_scan_now(self, instance):
        def _scan(dt):
            self._on_status_update("🔍 手动触发扫描...")
            config = load_config()
            new_audio, new_text = scan_all_files(self.watcher.processed_db)
            if not new_audio and not new_text:
                self._on_status_update("📭 未发现新文件")
                return
            total = len(new_audio) + len(new_text)
            self._on_status_update(f"🆕 发现 {total} 个新文件（录音{len(new_audio)}/文本{len(new_text)}）")

            for fpath in new_audio:
                fhash = file_hash(fpath)
                if not fhash:
                    continue
                ok = process_audio_file(fpath, config, self._on_status_update)
                self.watcher.stats["total_audio_processed"] += 1
                if ok:
                    self.watcher.stats["total_audio_pushed"] += 1
                self.watcher.processed_db[fhash] = {
                    "path": fpath, "type": "audio",
                    "processed_time": datetime.now().isoformat(),
                    "status": "pushed" if ok else "failed"
                }
                time.sleep(3)

            for fpath in new_text:
                fhash = file_hash(fpath)
                if not fhash:
                    continue
                ok = process_text_file(fpath, config, self._on_status_update)
                self.watcher.stats["total_text_processed"] += 1
                if ok:
                    self.watcher.stats["total_text_pushed"] += 1
                self.watcher.processed_db[fhash] = {
                    "path": fpath, "type": "text",
                    "processed_time": datetime.now().isoformat(),
                    "status": "pushed" if ok else "failed"
                }
                time.sleep(3)

            save_processed_db(self.watcher.processed_db)
            self._on_status_update("✅ 手动扫描完成")

        threading.Thread(target=lambda: Clock.schedule_once(_scan, 0), daemon=True).start()

    def on_settings(self, instance):
        cfg = load_config()
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))

        content.add_widget(Label(
            text="DeepSeek API Key:", size_hint_y=None, height=dp(30),
            color=(0.8, 0.8, 0.8, 1), halign="left"
        ))
        api_input = TextInput(
            text=cfg.get("deepseek_api_key", DEEPSEEK_API_KEY),
            size_hint_y=None, height=dp(40),
            multiline=False, font_size=dp(12)
        )
        content.add_widget(api_input)

        content.add_widget(Label(
            text="企微 Webhook URL:", size_hint_y=None, height=dp(30),
            color=(0.8, 0.8, 0.8, 1), halign="left"
        ))
        webhook_input = TextInput(
            text=cfg.get("webhook_url", WEBHOOK_URL),
            size_hint_y=None, height=dp(60),
            multiline=True, font_size=dp(11)
        )
        content.add_widget(webhook_input)

        def save_and_close(inst):
            cfg["deepseek_api_key"] = api_input.text.strip()
            cfg["webhook_url"] = webhook_input.text.strip()
            save_config(cfg)
            self._on_status_update("✅ 配置已保存")
            popup.dismiss()

        save_btn = Button(
            text="保存配置", size_hint_y=None, height=dp(44),
            background_color=(0.1, 0.6, 0.3, 1), background_normal=""
        )
        save_btn.bind(on_press=save_and_close)
        content.add_widget(save_btn)

        popup = Popup(title="⚙ 应用配置", content=content, size_hint=(0.95, 0.75))
        popup.open()

    def on_clear_log(self, instance):
        self.log_text.text = "日志已清除\n"


# ─────────────────────────────────────────────
# Kivy App 主类
# ─────────────────────────────────────────────

class Ai002App(App):
    def build(self):
        self.title = APP_NAME
        self.icon = "icon.png"
        return MainLayout()

    def on_start(self):
        log(f"{APP_NAME} {APP_VERSION} 启动")
        if platform == "android":
            self._request_android_permissions()

    def _request_android_permissions(self):
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.INTERNET,
                Permission.RECEIVE_BOOT_COMPLETED,
                Permission.FOREGROUND_SERVICE,
            ])
            log("Android 权限请求已发送")
        except ImportError:
            log("非 Android 环境，跳过权限请求")

    def on_pause(self):
        return True

    def on_resume(self):
        pass


if __name__ == "__main__":
    Ai002App().run()
