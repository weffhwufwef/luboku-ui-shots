#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在安卓模拟器里把 录播库 App 的每个页面「点一遍 + 截图」。

跑法(CI 里):
    python3 ci/drive.py            # 结果落盘到 shots/
依赖: 只有 adb + python3 标准库(uiautomator 用 adb shell 调)。

产物:
    shots/NN_name.png     每页截图
    shots/NN_name.xml     该页的 uiautomator 层级(点不到时用来复盘)
    shots/logcat.txt      全程 logcat(logcat 里能看出 inflate 崩 / 空指针)
    shots/report.md       每一步的结果
"""
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

PKG = "com.lubo.library"
MOCK = "http://10.0.2.2:8090"          # 模拟器里的宿主回环地址
SHOT_DIR = os.environ.get("SHOT_DIR", "shots")
SERIAL = os.environ.get("ANDROID_SERIAL", "")
REPORT = []
DUMPS = []


# ------------------------------------------------------------------ adb 基础

def adb(*a, binary=False, timeout=180):
    cmd = ["adb"] + (["-s", SERIAL] if SERIAL else []) + [str(x) for x in a]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return b"" if binary else "<timeout>"
    if binary:
        return r.stdout
    return (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")


def sh(*a, **kw):
    return adb("shell", *a, **kw)


def step(name, ok, note=""):
    REPORT.append(dict(step=name, ok=bool(ok), note=note))
    print(("  OK  " if ok else "  FAIL") + "  " + name + ("  " + note if note else ""), flush=True)


# ------------------------------------------------------------------ 界面读取

def dump_xml(tries=4, save_as=None):
    """uiautomator dump → 返回节点列表; 失败返回 []。"""
    last = ""
    for i in range(tries):
        sh("uiautomator", "dump", "/sdcard/ui.xml")
        x = adb("exec-out", "cat", "/sdcard/ui.xml")
        if x.strip().startswith("<?xml"):
            last = x
            break
        time.sleep(1.5)
    if not last:
        return []
    if save_as:
        try:
            open(os.path.join(SHOT_DIR, save_as), "w", encoding="utf-8").write(last)
        except Exception:
            pass
    try:
        root = ET.fromstring(last)
    except Exception:
        return []
    out = []
    for n in root.iter("node"):
        a = n.attrib
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", a.get("bounds", ""))
        if not m:
            continue
        l, t, r, b = (int(g) for g in m.groups())
        out.append(dict(
            text=(a.get("text") or "").strip(),
            rid=(a.get("resource-id") or "").split("/")[-1],
            desc=(a.get("content-desc") or "").strip(),
            cls=a.get("class") or "",
            clickable=a.get("clickable") == "true",
            bounds=(l, t, r, b),
            cx=(l + r) // 2, cy=(t + b) // 2,
        ))
    return out


def find(nodes, rid=None, text=None, contains=False, cls=None, clickable_only=False):
    for n in nodes:
        if clickable_only and not n["clickable"]:
            continue
        if rid and n["rid"] != rid:
            continue
        if cls and cls not in n["cls"]:
            continue
        if text is not None:
            if contains:
                if text not in n["text"] and text not in n["desc"]:
                    continue
            else:
                if n["text"] != text and n["desc"] != text:
                    continue
        return n
    return None


def tap(n):
    sh("input", "tap", n["cx"], n["cy"])
    return True


def tap_rid(rid, nodes=None, wait=0.0):
    nodes = nodes if nodes is not None else dump_xml()
    n = find(nodes, rid=rid)
    if not n:
        return False
    tap(n)
    if wait:
        time.sleep(wait)
    return True


def tap_text(text, contains=False, nodes=None, wait=0.0, prefer_bottom=False):
    nodes = nodes if nodes is not None else dump_xml()
    hits = [n for n in nodes if (text in n["text"] if contains else n["text"] == text)]
    if not hits:
        hits = [n for n in nodes if (text in n["desc"] if contains else n["desc"] == text)]
    if not hits:
        return False
    n = max(hits, key=lambda z: z["cy"]) if prefer_bottom else hits[0]
    tap(n)
    if wait:
        time.sleep(wait)
    return True


def type_text(s):
    sh("input", "text", s.replace(" ", "%s"))
    time.sleep(0.4)


def clear_field(rid, n=24):
    nodes = dump_xml()
    if tap_rid(rid, nodes):
        time.sleep(0.3)
        sh("input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(n):
            sh("input", "keyevent", "KEYCODE_DEL")
        return True
    return False


def swipe_up(times=1, dur=350):
    for _ in range(times):
        sh("input", "swipe", 540, 1800, 540, 700, dur)
        time.sleep(1.2)


def swipe_down(times=1):
    for _ in range(times):
        sh("input", "swipe", 540, 800, 540, 1900, 350)
        time.sleep(1.0)


def back(times=1):
    for _ in range(times):
        sh("input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.0)


def shot(name):
    data = adb("exec-out", "screencap", "-p", binary=True)
    path = os.path.join(SHOT_DIR, name + ".png")
    with open(path, "wb") as f:
        f.write(data)
    dump_xml(save_as=name + ".xml")
    size = os.path.getsize(path)
    step("shot:" + name, size > 20000, "%d bytes" % size)
    return size > 20000


def cur_activity():
    out = adb("shell", "dumpsys", "activity", "activities")
    m = re.findall(r"ResumedActivity: ActivityRecord\{[^}]*\s(\S+)\}", out)
    if not m:
        m = re.findall(r"mResumedActivity: ActivityRecord\{[^}]*\s(\S+)\}", out)
    return m[-1] if m else ""


def wait_activity(want, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        a = cur_activity()
        if want in a:
            time.sleep(1.6)          # 等首屏数据回来
            return True
        time.sleep(1.0)
    return False


def launch():
    sh("am", "start", "-n", PKG + "/.LoginActivity")
    time.sleep(3)


# ------------------------------------------------------------------ 前置: 服务端地址

def set_base_via_ui():
    """长按品牌块 → 服务端地址对话框 → 改成 CI 模拟服务端。"""
    nodes = dump_xml()
    b = find(nodes, rid="brandBlock")
    if not b:
        return False, "找不到品牌块(brandBlock)"
    sh("input", "swipe", b["cx"], b["cy"], b["cx"], b["cy"], 1200)   # 长按
    time.sleep(1.5)
    nodes = dump_xml()
    if not find(nodes, text="服务端地址", contains=True):
        return False, "长按没弹出「服务端地址」"
    ed = find(nodes, cls="EditText")
    if not ed:
        return False, "对话框里没有输入框"
    tap(ed)
    time.sleep(0.4)
    sh("input", "keyevent", "KEYCODE_MOVE_END")
    for _ in range(40):
        sh("input", "keyevent", "KEYCODE_DEL")
    type_text(MOCK)
    time.sleep(0.5)
    ok = tap_text("保存")
    time.sleep(2.5)
    return ok, ("已切到 " + MOCK if ok else "没点到「保存」")


def set_base_via_prefs():
    """兜底: root 后直接写 SharedPreferences。"""
    adb("root")
    time.sleep(2)
    xml = ("<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<map>\n"
           "    <string name=\"base\">%s</string>\n</map>\n" % MOCK)
    tmp = "/data/local/tmp/lubo_prefs.xml"
    local = os.path.join(SHOT_DIR, "_prefs.xml")
    open(local, "w").write(xml)
    adb("push", local, tmp)
    sh("am", "force-stop", PKG)
    time.sleep(1)
    sh("mkdir", "-p", "/data/data/%s/shared_prefs" % PKG)
    sh("cp", tmp, "/data/data/%s/shared_prefs/lubo.xml" % PKG)
    uid = ""
    m = re.search(r"userId=(\d+)", adb("shell", "dumpsys", "package", PKG))
    if m:
        uid = m.group(1)
        sh("chown", "%s:%s" % (uid, uid), "/data/data/%s/shared_prefs/lubo.xml" % PKG)
        sh("chmod", "660", "/data/data/%s/shared_prefs/lubo.xml" % PKG)
    return uid != ""


# ------------------------------------------------------------------ 走查

def walk():
    os.makedirs(SHOT_DIR, exist_ok=True)

    step("prepare: 关动画/常亮", True, sh("settings", "put", "global", "window_animation_scale", "0")[:0] or "")
    sh("settings", "put", "global", "transition_animation_scale", "0")
    sh("settings", "put", "global", "animator_duration_scale", "0")
    sh("svc", "power", "stayon", "true")
    print("屏幕: " + sh("wm", "size").strip().replace("\n", " "))

    # 清掉上一轮的状态
    sh("pm", "clear", PKG)
    launch()

    # ---------- 登录页
    ok, note = set_base_via_ui()
    if not ok:
        step("设置服务端地址(UI)", False, note)
        st = set_base_via_prefs()
        step("设置服务端地址(root 兜底)", st, "uid=" + str(st))
        launch()
    else:
        step("设置服务端地址(UI)", True, note)
    time.sleep(1.5)
    shot("01_login_normal")

    # 错误态: 故意输错密码
    if clear_field("account"):
        type_text("ci")
    tap_rid("password")
    type_text("wrong")
    tap_rid("captcha")
    type_text("abcd")
    if tap_rid("login", wait=4.0):
        shot("02_login_error")
    else:
        step("登录(错误态)", False, "找不到登录按钮")

    # 正常登录
    clear_field("password")
    tap_rid("password")
    type_text("ci1234")
    clear_field("captcha")
    tap_rid("captcha")
    type_text("abcd")
    if tap_rid("login", wait=3.0):
        got = wait_activity("MainActivity", 25)
        step("登录(正常) → 录播库", got, cur_activity())
    else:
        step("登录(正常)", False, "点不到登录按钮")
    time.sleep(1.5)

    # ---------- 录播库
    shot("03_lib_top")
    swipe_up(2)
    shot("04_lib_scrolled")
    swipe_down(3)

    # ---------- 公告抽屉
    if tap_rid("libBell", wait=2.5):
        shot("05_announce_sheet")
        if tap_text("服务端已升级到 v2 界面", contains=True, wait=1.5):
            shot("06_announce_dialog")
            tap_text("好") or back()
        else:
            step("公告详情", False, "抽屉里没找到公告条目")
            back()
    else:
        step("公告入口", False, "找不到 libBell")

    # ---------- 搜索
    if tap_rid("libSearch", wait=3.0):
        shot("07_search_empty")
        nodes = dump_xml()
        ed = find(nodes, cls="EditText")
        if ed:
            tap(ed)
            type_text("lu")
            if tap_text("搜索", contains=False, wait=3.0) or sh("input", "keyevent", "KEYCODE_ENTER"):
                time.sleep(2.5)
                shot("08_search_results")
        else:
            step("搜索输入框", False, "页面上没有 EditText")
        back()
    else:
        step("搜索入口", False, "找不到 libSearch")

    # ---------- 录制
    if tap_rid("tbRec", wait=3.0) or wait_activity("RecordActivity", 8):
        shot("09_record_top")
        swipe_up(2)
        shot("10_record_scrolled")
    else:
        step("录制 Tab", False, cur_activity())

    # ---------- 下载
    if tap_rid("tbDl", wait=3.0) or wait_activity("FilesActivity", 8):
        shot("11_files_top")
        swipe_up(2)
        shot("12_files_scrolled")
    else:
        step("下载 Tab", False, cur_activity())

    # ---------- 我的
    if tap_rid("tbMe", wait=3.0) or wait_activity("MeActivity", 8):
        shot("13_me_top")
        swipe_up(2)
        shot("14_me_scrolled")
    else:
        step("我的 Tab", False, cur_activity())

    # ---------- 我的权限 / 观看记录
    if tap_text("我的权限", contains=True, wait=3.0) or wait_activity("PermActivity", 6):
        shot("15_perm")
        back()
    else:
        step("我的权限", False, cur_activity())

    swipe_up(1)
    if tap_text("观看记录", contains=True, wait=3.0) or wait_activity("HistoryActivity", 6):
        shot("16_history")
        swipe_up(2)
        shot("17_history_scrolled")
        back()
    else:
        step("观看记录", False, cur_activity())

    # ---------- 后台管理(5 个分段)
    swipe_up(1)
    if tap_text("后台管理", contains=True, wait=3.5) or wait_activity("UsersActivity", 8):
        shot("18_admin_users")
        swipe_up(2)
        shot("19_admin_users_more")
        for seg, nm in (("站点", "20_admin_site"), ("空间", "21_admin_space"),
                        ("公告", "22_admin_notice"), ("记录", "23_admin_hist")):
            if tap_text(seg, contains=True, wait=3.0):
                shot(nm)
                swipe_up(1)
                shot(nm + "_scrolled")
                swipe_down(2)
            else:
                step("后台分段:" + seg, False, "找不到分段按钮")
        back()
    else:
        step("后台管理", False, cur_activity())

    # ---------- 全部主播 / 主播详情
    if tap_rid("tbLib", wait=3.0) or wait_activity("MainActivity", 8):
        pass
    if tap_text("全部", contains=True, wait=3.0) or wait_activity("AllStreamers", 6):
        shot("24_streamers")
        if tap_text("小美", contains=False, wait=3.5) or wait_activity("StreamerActivity", 8):
            shot("25_streamer")
            swipe_up(2)
            shot("26_streamer_scrolled")
            back()
        else:
            step("进主播详情", False, cur_activity())
        back()

    # ---------- 播放器(能点开就截一张, 播不播得动另说)
    if tap_rid("tbLib", wait=2.5):
        nodes = dump_xml()
        cand = [n for n in nodes if n["clickable"] and n["cy"] > 700]
        if cand:
            tap(cand[0])
            if wait_activity("PlayerActivity", 8):
                time.sleep(3)
                shot("27_player")
                back()
            else:
                step("播放器", False, "点了卡片没进 PlayerActivity: " + cur_activity())
        else:
            step("播放器", False, "首页找不到可点的卡片")


def main():
    os.makedirs(SHOT_DIR, exist_ok=True)
    try:
        walk()
    except Exception as e:
        import traceback
        step("walk 异常", False, str(e))
        print(traceback.format_exc())

    log = adb("logcat", "-d", "-v", "time")
    open(os.path.join(SHOT_DIR, "logcat.txt"), "w", encoding="utf-8").write(log)
    bad = [l for l in log.splitlines()
           if ("FATAL EXCEPTION" in l or "InflateException" in l or "AndroidRuntime" in l
               or "NullPointerException" in l or "ClassNotFoundException" in l)]
    open(os.path.join(SHOT_DIR, "logcat_errors.txt"), "w", encoding="utf-8").write("\n".join(bad))
    print("logcat 里可疑行数: %d" % len(bad))
    for l in bad[:20]:
        print("   " + l[:200])

    api_log = ""
    try:
        import urllib.request
        api_log = urllib.request.urlopen(MOCK.replace("10.0.2.2", "127.0.0.1") + "/__log", timeout=5).read().decode()
    except Exception as e:
        api_log = "取服务端请求日志失败: %s" % e
    open(os.path.join(SHOT_DIR, "mock_requests.txt"), "w", encoding="utf-8").write(api_log)

    lines = ["# 页面走查报告", "", "| 步骤 | 结果 | 说明 |", "|---|---|---|"]
    for r in REPORT:
        lines.append("| %s | %s | %s |" % (r["step"], "✅" if r["ok"] else "❌", r["note"]))
    lines += ["", "logcat 可疑行: %d（见 logcat_errors.txt）" % len(bad), "",
              "## 服务端收到的请求", "```", api_log[:4000], "```"]
    open(os.path.join(SHOT_DIR, "report.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("报告: %s/report.md" % SHOT_DIR)
    for f in sorted(os.listdir(SHOT_DIR)):
        if f.endswith(".png"):
            print("   %s  %d bytes" % (f, os.path.getsize(os.path.join(SHOT_DIR, f))))


if __name__ == "__main__":
    main()
