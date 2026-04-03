[app]
# ─────────────────────────────────────────────
# Ai002-工具流-手机录音-智能解析
# Buildozer 打包配置文件
# Buildozer.io 云端编译专用
# ─────────────────────────────────────────────

title = Ai002录音智能解析
package.name = ai002recording
package.domain = com.himalaya.ai002
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.1.0

# Buildozer.io 稳定依赖（去掉 kivy，仅用 pyjnius 后台运行）
requirements = python3,kivy,requests,android

# Android 屏幕方向
orientation = portrait

# Android 权限
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,INTERNET,RECEIVE_BOOT_COMPLETED,FOREGROUND_SERVICE,ACCESS_NETWORK_STATE

# Android API 级别
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33

# 支持 64 位
android.archs = arm64-v8a, armeabi-v7a

# 允许后台运行
android.wakelock = True

# 日志等级（发布时改为 2）
log_level = 1

# 去掉 icon 引用（Buildozer 使用默认图标）
# icon.filename = %(source.dir)s/icon.png

[buildozer]
log_level = 1
warn_on_root = 1
