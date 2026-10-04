#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在安卓模拟器里把 录播库 App 的每个页面「点一遍 + 截图」。

跑法(CI 里): SHOT_DIR=shots python3 ci/drive.py
依赖: 只有 adb + python3 标准库(uiautomator 用 adb shell 调)。

产物:
    shots/NN_name.png     每页截图
    shots/NN_name.xml     该页的 uiautomator 层级(点不到时用来复盘)
    shots/logcat.txt      全程 logcat
    shots/logcat_errors.txt / report.md / mock_requests.txt

踩过的坑(别再犯):
  1. 软键盘弹起时, 屏幕底部的 TabBar 被键盘盖住 → `input tap` 落在键盘上, 点什么都没反应。
     所以点底部 Tab 之前先 hide_ime(), 点完还要 wait_activity 校验页面真的换了。
  2. `dumpsys activity activities` 里 ResumedActivity 那行最后一段是任务号 `t9}`,
     取 Activity 名要匹配带 '/' 的 token, 否则会得到 "t9"(第一版就踩了这个)。
"""
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET

PKG = "com.lubo.library"
MOCK = "http://10.0.2.2:8090"          # 模拟器里的宿主回环地址
SHOT_DIR = os.environ.get("SHOT_DIR", "shots")
SERIAL = os.environ.get("ANDROID_SERIAL", "")
REPORT = []


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
    for _ in range(tries):
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


def find(nodes, rid=None, text=None, contains=False, cls=None):
    for n in nodes:
        if rid and n["rid"] != rid:
            continue
        if cls and cls not in n["cls"]:
            continue
        if text is not None:
            hay = n["text"] + " " + n["desc"]
            if contains:
                if text not in hay:
                    continue
            elif text not in (n["text"], n["desc"]):
                continue
        return n
    return None


def tap(n, pause=1.2):
    sh("input", "tap", n["cx"], n["cy"])
    time.sleep(pause)


def tap_rid(rid, nodes=None, pause=1.2):
    nodes = nodes if nodes is not None else dump_xml()
    n = find(nodes, rid=rid)
    if not n:
        return False
    tap(n, pause)
    return True


def tap_text(text, contains=False, nodes=None, pause=1.2, prefer="first"):
    nodes = nodes if nodes is not None else dump_xml()
    hits = [n for n in nodes if (text in (n["text"] + " " + n["desc"]) if contains
                                 else text in (n["text"], n["desc"]))]
    if not hits:
        return False
    n = min(hits, key=lambda z: z["cy"]) if prefer == "first" else max(hits, key=lambda z: z["cy"])
    tap(n, pause)
    return True


def type_text(s):
    sh("input", "text", s.replace(" ", "%s"))
    time.sleep(0.5)


def clear_field(rid, n=24):
    nodes = dump_xml()
    if tap_rid(rid, nodes, 0.4):
        sh("input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(n):
            sh("input", "keyevent", "KEYCODE_DEL")
        return True
    return False


def ime_shown():
    return "mInputShown=true" in adb("shell", "dumpsys", "input_method")


def hide_ime(tries=3):
    """软件键盘会盖住底部 TabBar → 点 Tab 前先收掉(按 BACK 只收键盘, 页面不变)。"""
    for _ in range(tries):
        if not ime_shown():
            return True
        sh("input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.0)
    return not ime_shown()


def swipe_up(times=1, dur=350):
    for _ in range(times):
        sh("input", "swipe", 540, 1700, 540, 700, dur)
        time.sleep(1.3)


def swipe_down(times=1):
    for _ in range(times):
        sh("input", "swipe", 540, 800, 540, 1800, 350)
        time.sleep(1.1)


def back(times=1, pause=1.2):
    for _ in range(times):
        sh("input", "keyevent", "KEYCODE_BACK")
        time.sleep(pause)


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
    """当前栈顶 Activity 类名(如 MainActivity); 取不到返回 ''。"""
    out = adb("shell", "dumpsys", "activity", "activities")
    m = re.findall(r"ResumedActivity:.*?([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)", out)
    if not m:
        m = re.findall(r"mResumedActivity:.*?([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)", out)
    if not m:
        w = adb("shell", "dumpsys", "window", "windows")
        m = re.findall(r"mCurrentFocus=Window\{[^}]*\s([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)", w)
    return m[-1].split("/")[-1] if m else ""


def wait_activity(want, timeout=20, settle=1.5):
    end = time.time() + timeout
    while time.time() < end:
        if want in cur_activity():
            time.sleep(settle)
            return True
        time.sleep(0.8)
    return False


def goto(want, rid=None, text=None, contains=False, tries=4):
    """点入口并**校验真的到了目标页**: 收键盘 → 点 → 等 Activity; 不成重试。"""
    for i in range(tries):
        hide_ime()
        nodes = dump_xml()
        ok = tap_rid(rid, nodes, 1.8) if rid else tap_text(text, contains, nodes, 1.8)
        if not ok:
            return False, "第%d次: 找不到入口(%s)" % (i + 1, rid or text)
        if wait_activity(want, 10):
            return True, want
    return False, "点了 %d 次都没进 %s, 当前=%s" % (tries, want, cur_activity())


def app_bottom():
    """App 窗口底边(= 系统导航栏顶边)。

    关键: 别拿 uiautomator 里的坐标, 也别拿 dumpsys 里最大的那个窗口 ——
    · uiautomator 把底部 TabBar 报成「到窗口底部就被截断 / 四个格子 0x0」
      (窗口元数据还是软键盘弹起时的旧值), 按它点等于点在屏幕外;
    · 屏幕上最大的窗口是全屏 0→2340, 底部 2208→2340 是**系统导航栏**,
      照它算 y 会点到返回/Home 手势上(上一轮就这么把 App 点回了桌面)。
    """
    out = adb("shell", "dumpsys", "window", "windows")
    m = re.search(r"ITYPE_NAVIGATION_BAR, mFrame=\[\d+,(\d+)\]\[\d+,(\d+)\]", out)
    if m:
        return int(m.group(1))
    m2 = re.search(r"ITYPE_IME, mFrame=\[\d+,(\d+)\]\[\d+,(\d+)\], mVisible", out)
    if m2:
        return int(m2.group(2)) - 140
    m3 = re.search(r"(\d+)x(\d+)", sh("wm", "size"))
    return int(m3.group(2)) - 140 if m3 else 2208


def goto_tab(idx, want, tries=4):
    """点底部第 idx 个 Tab(0=录播库; 重构后只有 3 个 Tab), 坐标按「导航栏往上」自己算, 点完校验 Activity。"""
    l, r, btm = 0, 1080, app_bottom()
    m = re.search(r"(\d+)x(\d+)", sh("wm", "size"))
    if m:
        r = int(m.group(1))
    xs = [int((idx + 0.5) * r / 3), int((idx + 0.5) * r / 4)]
    cands = [(x, y) for x in xs for y in (btm - 79, btm - 50, btm - 40, btm - 110, btm - 150)]
    for i in range(tries):
        hide_ime()
        for x, y in cands:
            sh("input", "tap", x, y)
            time.sleep(1.6)
            if wait_activity(want, 8):
                step("tab%d → %s" % (idx, want), True, "点击 (%d,%d)" % (x, y))
                return True
    # 兜底: 直接 am start(和点 Tab 走的是同一个 Intent), 但如实标注「点击没生效」
    cls = ("MainActivity", "RecordActivity", "MeActivity")[idx]
    sh("am", "start", "-n", "%s/.%s" % (PKG, cls))
    if wait_activity(want, 15):
        step("tab%d → %s" % (idx, want), True,
             "⚠️ 点 Tab 没生效, 用 am start 进的页面(底边=%d, 当前=%s)" % (btm, cur_activity()))
        return True
    step("tab%d → %s" % (idx, want), False, "底边=%d, 点了 %d 个坐标 + am start 都没进, 当前=%s"
         % (btm, len(cands), cur_activity()))
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
    tap(ed, 0.4)
    sh("input", "keyevent", "KEYCODE_MOVE_END")
    for _ in range(40):
        sh("input", "keyevent", "KEYCODE_DEL")
    type_text(MOCK)
    time.sleep(0.5)
    ok = tap_text("保存", pause=2.5)
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
    sh("settings", "put", "global", "window_animation_scale", "0")
    sh("settings", "put", "global", "transition_animation_scale", "0")
    sh("settings", "put", "global", "animator_duration_scale", "0")
    sh("svc", "power", "stayon", "true")
    step("prepare", True, sh("wm", "size").strip().replace("\n", " ") + " / " +
         sh("wm", "density").strip().replace("\n", " "))

    sh("pm", "clear", PKG)
    launch()

    # ---------------- 登录页
    ok, note = set_base_via_ui()
    step("设置服务端地址(长按品牌块)", ok, note)
    if not ok:
        set_base_via_prefs()
        launch()
    time.sleep(1.5)
    hide_ime()
    shot("01_login_normal")

    # 错误态(密码故意输错; 模拟服务端回 401 + <div class="err">)
    clear_field("account")
    tap_rid("account", pause=0.3)
    type_text("ci")
    clear_field("password")
    tap_rid("password", pause=0.3)
    type_text("wrong")
    clear_field("captcha")
    tap_rid("captcha", pause=0.3)
    type_text("abcd")
    hide_ime()
    if tap_rid("login", pause=4.0):
        shot("02_login_error")
    else:
        step("登录(错误态)", False, "找不到登录按钮")

    # 正常登录
    clear_field("password")
    tap_rid("password", pause=0.3)
    type_text("ci1234")
    clear_field("captcha")
    tap_rid("captcha", pause=0.3)
    type_text("abcd")
    hide_ime()
    tap_rid("login", pause=3.0)
    got = wait_activity("MainActivity", 25)
    step("登录(正常) → 录播库", got, cur_activity())
    if not got:
        shot("03_login_FAIL")
        return

    # ---------------- 录播库
    time.sleep(1.5)
    shot("03_lib_top")
    swipe_up(2)
    shot("04_lib_scrolled")
    swipe_down(3)

    # 公告抽屉
    if tap_rid("libBell", pause=2.5):
        shot("05_announce_sheet")
        if tap_text("服务端已升级到 v2 界面", contains=True, pause=1.8):
            shot("06_announce_dialog")
            # 2026-10-04 起公告详情是底部抽屉(可下拖取消), 收尾改点「取消」行
            if not tap_text("取消", pause=1.0):
                back()
        else:
            step("公告详情", False, "抽屉里没找到公告条目")
            back()
    else:
        step("公告入口", False, "找不到 libBell")

    # 全部主播(首页「6 位 · 全部 ›」整行可点)
    ok2, note2 = goto("AllStreamersActivity", text="位 · 全部", contains=True)
    if ok2:
        shot("07_streamers")
        swipe_up(2)
        shot("08_streamers_scrolled")
        swipe_down(2)
        back()
    else:
        step("全部主播", False, note2)
        shot("07_streamers_FAIL")

    # 主播详情(点监控区的主播卡)
    if tap_text("小美", pause=1.5) and wait_activity("StreamerActivity", 12):
        shot("09_streamer")
        swipe_up(2)
        shot("10_streamer_scrolled")
        back()
    else:
        step("主播详情", False, "点了主播卡没进 StreamerActivity: " + cur_activity())
        shot("09_streamer_FAIL")

    # 播放器(设计稿 ① 竖屏 + ①b 横屏全屏): 舞台/控制层/分段条/横屏
    nodes = dump_xml()
    card = None
    for n in nodes:                                      # 优先挑多段场次(分段条才有 2 张以上的卡可切)
        m2 = re.match(r"^(\d+) 段", n["text"])
        if m2 and int(m2.group(1)) >= 2:
            card = n
            break
    if card is None:
        for n in nodes:
            if re.match(r"^\d+:\d\d(:\d\d)?$", n["text"]):
                card = n
                break
    if card is None:
        cand = [n for n in nodes if n["clickable"] and 1200 < n["cy"] < 1900]
        card = cand[0] if cand else None
    if card is not None:
        tap(card, 2.0)
        if wait_activity("PlayerActivity", 12, settle=3.0):
            hide_ime()
            shot("11_player_portrait")
            # 2026-10-04 新口径: 播放中点画面 = 暂停(顺带截到中央大播放钮 + 分段进度条)
            sh("input", "tap", 540, 530)
            time.sleep(1.6)
            shot("11g_player_paused")
            sh("input", "tap", 540, 530)                     # 再点一下继续播
            time.sleep(1.2)
            tap_text("分段 2", pause=2.2)                 # 分段条: 点第 2 张分段卡切段
            shot("11b_player_seg2")
            if tap_rid("fs", pause=3.5):                 # 竖屏点全屏 = 请求横屏(不做竖屏假全屏)
                shot("11c_player_landscape")
                tap_rid("fs", pause=3.0)                 # 横屏回竖屏
                shot("11d_player_back_portrait")
            else:
                step("播放器全屏按钮", False, "找不到 fs")
            if tap_rid("segbtn", pause=2.2):             # 顶栏 ⋯ = 播放设置
                shot("11e_player_settings")
                back()
            back()
        else:
            step("播放器", False, "点了场次卡没进 PlayerActivity: " + cur_activity())
            shot("11_player_FAIL")
    else:
        step("播放器", False, "首页没找到场次卡")

    # 直播中的场次: 「录制中」角标 + 末段时长显示「录制中」(mock 里小美那场是 live.m3u8)
    def find_live():
        for n in dump_xml():
            if "录制中" in n["text"] and len(n["text"]) > 4:
                return n
        return None

    live = find_live()
    if live is None:
        swipe_up(1)
        live = find_live()
    if live is not None:
        tap(live, 2.0)
        if wait_activity("PlayerActivity", 12, settle=3.0):
            hide_ime()
            shot("11f_player_live")
            back()
        else:
            step("直播播放器", False, "点了直播场次卡没进 PlayerActivity: " + cur_activity())
    else:
        step("直播场次卡", False, "列表里找不到「录制中」字样的卡片")

    # ---------------- 录制 / 我的(下载已并入「我的 → 我的下载」, 不再是底部 Tab)
    for idx, want, a, b in ((1, "RecordActivity", "12_record_top", "13_record_scrolled"),
                            (2, "MeActivity", "16_me_top", "17_me_scrolled")):
        if goto_tab(idx, want):
            shot(a)
            swipe_up(2)
            shot(b)
            swipe_down(2)
        else:
            shot(a + "_FAIL")

    # ---------------- 我的 → 我的权限 / 观看记录 / 后台管理
    if wait_activity("MeActivity", 6):
        ok4, note4 = goto("PermActivity", text="我的权限", contains=True)
        if ok4:
            shot("18_perm")
            back()
        else:
            step("我的权限", False, note4)
            shot("18_perm_FAIL")

        swipe_up(1)
        ok5, note5 = goto("HistoryActivity", text="观看记录", contains=True)
        if ok5:
            shot("19_history")
            swipe_up(2)
            shot("20_history_scrolled")
            back()
        else:
            step("观看记录", False, note5)
            shot("19_history_FAIL")

        swipe_up(1)
        ok6, note6 = goto("UsersActivity", text="后台管理", contains=True)
        if ok6:
            shot("21_admin_users")
            swipe_up(2)
            shot("22_admin_users_more")
            for seg, nm in (("站点", "23_admin_site"), ("存储", "24_admin_space"),
                            ("公告", "25_admin_notice"), ("观看记录", "26_admin_hist")):
                if tap_text(seg, pause=2.0):
                    shot(nm)
                    swipe_up(1)
                    shot(nm + "_scrolled")
                    swipe_down(2)
                else:
                    step("后台分段:" + seg, False, "找不到分段按钮")
                    shot("FAIL_admin_" + seg)
            back()
        else:
            step("后台管理", False, note6)
            shot("21_admin_FAIL")
    else:
        step("我的 Tab", False, "不在 MeActivity: " + cur_activity())

    # ---------------- 搜索(放最后: 要打字, 键盘会挡住底部)
    if goto_tab(0, "MainActivity") and tap_rid("libSearch", pause=3.0):
        shot("27_search_empty")
        nodes = dump_xml()
        ed = find(nodes, cls="EditText")
        if ed:
            tap(ed, 0.4)
            type_text("lu")
            if not tap_text("搜索", pause=3.0):
                sh("input", "keyevent", "KEYCODE_ENTER")
                time.sleep(2.5)
            hide_ime()
            time.sleep(1.0)
            shot("28_search_results")
        else:
            step("搜索输入框", False, "页面上没有 EditText")
            shot("27_search_FAIL")
    else:
        step("搜索", False, "没进搜索页: " + cur_activity())


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
               or "NullPointerException" in l or "ClassNotFoundException" in l
               or "Resources$NotFound" in l)]
    bad = [l for l in bad if "com.android.commands" not in l and "ZygoteInit" not in l]
    open(os.path.join(SHOT_DIR, "logcat_errors.txt"), "w", encoding="utf-8").write("\n".join(bad))
    print("logcat 可疑行数: %d" % len(bad))
    for l in bad[:20]:
        print("   " + l[:200])

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
              "## 服务端收到的请求", "```", api_log[:6000], "```"]
    open(os.path.join(SHOT_DIR, "report.md"), "w", encoding="utf-8").write("\n".join(lines))
    print("报告: %s/report.md" % SHOT_DIR)
    for f in sorted(os.listdir(SHOT_DIR)):
        if f.endswith(".png"):
            print("   %s  %d bytes" % (f, os.path.getsize(os.path.join(SHOT_DIR, f))))


if __name__ == "__main__":
    main()
