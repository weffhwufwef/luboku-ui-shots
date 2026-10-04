#!/usr/bin/env bash
# 模拟器起来之后在 runner 上跑的东西: 装 APK → 逐页走查截图。
# 注意: android-emulator-runner 的 script 是**逐行**丢给 sh -c 执行的(变量不跨行),
# 所以真正的逻辑必须放在这个文件里, workflow 里只写 `bash ci/run.sh`。
set -euxo pipefail

adb devices
adb shell getprop ro.build.version.release
adb shell getprop ro.product.cpu.abi

APK="${APK:-app/lubo-1.18.apk}"
echo "被测 APK: $APK"
adb install -r "$APK"
adb shell pm list packages | grep lubo || true
adb shell dumpsys package com.lubo.library | grep -E "versionName|versionCode" | head -3 || true

# 屏幕尺寸/密度存档(截图坐标靠它复盘)
adb shell wm size || true
adb shell wm density || true
# App 窗口真实矩形(TabBar 点击坐标按它算; uiautomator 里底部那条的坐标不可信)
adb shell dumpsys window windows | grep -E "mFrame=|mCurrentFocus" | head -20 || true

# 上一轮提交回仓库的截图会被 checkout 出来, 先清掉, 免得新旧混在一起分不清
rm -rf shots

SHOT_DIR=shots python3 ci/drive.py
