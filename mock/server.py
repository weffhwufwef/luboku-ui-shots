#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
录播库 App 的「CI 模拟服务端」——只用 Python 标准库, 在 GitHub Actions 的模拟器里
代替 47.122.106.244 真服务端, 让 App 的每个页面都能拿到一份形状正确、内容可控的数据。

数据口径全部照 luboku-android 客户端解析处抄:
  /api/videos.json          ← Video.from(): key/title/anchor/url/thumbnail/avatar/recorded_at/
                              resolution/duration/position/size/alive/expire_at/expire_left/
                              keep_forever/keep_priority/owner
  /api/record/status.json   ← RcRows: monitors[]/oneoff[]/today[]/past[]/now/is_admin/
                              keep_hours/jobs{}/owner_ids{}
  /api/me.json              ← {user:{...}, perms:{record,delete,files,users}}
  /api/links.json           ← 下载中心条目(数组)
  /api/users.json           ← {users:[...], exp_presets:{}}
  /api/site.json            ← {site:{icp,icp_link}}
  /api/admin/storage.json   ← {record_disk,sys_disk,library:{by_anchor,top},overflow,policy,files,ts}
  /api/watch/history.json   ← {history:[{key,title,position,duration,watched_at}]}
  /api/announcements.json   ← {announcements:[{title,body,date}]}
时间字段一律**相对当前时刻动态生成**(北京时间), 这样在 CI 上永远有「今日」场次。

用法: python3 server.py [--port 8090] [--dir fixtures]
"""
import argparse
import datetime
import hashlib
import json
import random
import re
import struct
import sys
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BJ = datetime.timezone(datetime.timedelta(hours=8))
SESS = "lubo_sess=ci-" + hashlib.sha1(b"luboku-ci").hexdigest()[:12]
LOG = []
LOCK = threading.Lock()


def now_bj():
    return datetime.datetime.now(BJ)


def fmt(dt, pat="%Y-%m-%d %H:%M"):
    return dt.strftime(pat)


def ago(hours=0.0, minutes=0.0):
    return now_bj() - datetime.timedelta(hours=hours, minutes=minutes)


def stamp_of(dt):
    """场地目录时间戳口径: 20261003_2115"""
    return dt.strftime("%Y%m%d_%H%M")


# --------------------------------------------------------------------------- 数据

def anchor_names():
    return ["小美", "阿泽", "大坤", "老白", "Luna", "超级无敌长的主播名字用来试溢出"]


def make_sessions():
    """一场直播 = 一个目录, 可能多段 _pN.mp4。返回 [(dir, [parts...])]"""
    out = []
    # 1) 小美 · 今天正在直播 (m3u8) + 优先保留
    d1 = "rec/" + stamp_of(ago(hours=3.5)) + "_xiaomei"
    out.append((d1, [
        dict(key=d1 + "/live.m3u8", dur=12840, size=1_510_000_000, res="1080p60",
             keep_priority=True, recorded=ago(hours=3.5)),
    ]))
    # 2) 阿泽 · 今天 3 段的场次(测多段合并)
    d2 = "rec/" + stamp_of(ago(hours=7.2)) + "_aze"
    out.append((d2, [
        dict(key=d2 + "/live_p1.mp4", dur=4210, size=520_000_000, res="1080p", recorded=ago(hours=7.2)),
        dict(key=d2 + "/live_p2.mp4", dur=1290, size=160_000_000, res="1080p", recorded=ago(hours=6.5)),
        dict(key=d2 + "/live_p3.mp4", dur=7380, size=910_000_000, res="1080p", recorded=ago(hours=5.4)),
    ]))
    # 3) 大坤 · 今天, 永久保留, 剩余 36 分钟(测红字告警)
    d3 = "rec/" + stamp_of(ago(hours=9.1)) + "_dakun"
    out.append((d3, [
        dict(key=d3 + "/live_p1.mp4", dur=9060, size=1_180_000_000, res="720p", recorded=ago(hours=9.1),
             keep_forever=True, left=2160),
    ]))
    # 4) 小美 · 昨天 第二场(同一主播两场)
    d4 = "rec/" + stamp_of(ago(hours=27)) + "_xiaomei"
    out.append((d4, [
        dict(key=d4 + "/live_p1.mp4", dur=6480, size=845_000_000, res="1080p", recorded=ago(hours=27), left=61200),
        dict(key=d4 + "/live_p2.mp4", dur=1500, size=190_000_000, res="1080p", recorded=ago(hours=26), left=61200),
    ]))
    # 5) 老白 · 前天的场次, 已归档(alive=false)
    d5 = "rec/" + stamp_of(ago(hours=51)) + "_laobai"
    out.append((d5, [
        dict(key=d5 + "/live_p1.mp4", dur=3300, size=430_000_000, res="480p", recorded=ago(hours=51),
             alive=False, left=-3600),
    ]))
    # 6) Luna · 前天(ASCII 名, 用来测搜索)
    d6 = "rec/" + stamp_of(ago(hours=56)) + "_luna"
    out.append((d6, [
        dict(key=d6 + "/live_p1.mp4", dur=2520, size=300_000_000, res="720p", recorded=ago(hours=56), left=86400),
    ]))
    # 7) 超长名 · 今天(测文字溢出/换行)
    d7 = "rec/" + stamp_of(ago(hours=2.0)) + "_longname"
    out.append((d7, [
        dict(key=d7 + "/live_p1.mp4", dur=15900, size=2_450_000_000, res="1080p60", recorded=ago(hours=2.0)),
    ]))
    return out


SESSIONS = make_sessions()


def videos(all_=False):
    out = []
    for d, parts in SESSIONS:
        anchor = d.split("_")[-1].replace("xiaomei", "小美").replace("aze", "阿泽") \
            .replace("dakun", "大坤").replace("laobai", "老白").replace("luna", "Luna") \
            .replace("longname", "超级无敌长的主播名字用来试溢出")
        for i, p in enumerate(parts, 1):
            alive = p.get("alive", True)
            if not alive and not all_:
                continue
            out.append({
                "key": p["key"],
                "title": anchor + " 【" + p["key"].split("/")[-1] + "】",
                "anchor": anchor,
                "url": "http://10.0.2.2:8090/media/" + p["key"].split("/")[-1],
                "thumbnail": "",
                "avatar": "",
                "recorded_at": fmt(p["recorded"]),
                "resolution": p["res"],
                "duration": p["dur"],
                "position": 0 if i == 1 else 0,
                "size": p["size"],
                "alive": alive,
                "expire_at": 0 if p.get("keep_forever") else (now_bj().timestamp() + p.get("left", 3 * 86400)) * 1,
                "expire_left": p.get("left", 3 * 86400),
                "keep_forever": bool(p.get("keep_forever")),
                "keep_priority": bool(p.get("keep_priority")),
                "owner": "" ,
            })
    out.sort(key=lambda v: v["recorded_at"], reverse=True)
    return out


def monitors():
    m1 = dict(name="小美", room_id="7758521", recording=True, live=True,
              current=dict(start_bj=fmt(ago(hours=3.5)), duration=12840, size=1_510_000_000,
                           segments=27, clips=27, parts=1))
    m1["live_checked_at"] = now_bj().timestamp()
    m2 = dict(name="阿泽", room_id="6600123", recording=False, live=True, manual_stopped=False,
              last_session=fmt(ago(hours=7.2)), last_end=fmt(ago(hours=5.1)))
    m2["live_checked_at"] = now_bj().timestamp()
    m3 = dict(name="大坤", room_id="", recording=False, live=False, manual_stopped=False,
              live_checked_at=0)                     # 待检测
    m4 = dict(name="老白", room_id="1122334", recording=False, live=True, manual_stopped=True,
              live_checked_at=now_bj().timestamp())  # 已手动停止
    m5 = dict(name="Luna", room_id="", recording=False, live=False, live_err="连接超时",
              live_checked_at=now_bj().timestamp())  # 检测失败
    m6 = dict(name="超级无敌长的主播名字用来试溢出", room_id="8899001", recording=False, live=False,
              live_checked_at=now_bj().timestamp())
    return [m1, m2, m3, m4, m5, m6]


def record_status():
    t_today = []
    for d, parts in SESSIONS:
        anchor = d.split("_")[-1].replace("xiaomei", "小美").replace("aze", "阿泽") \
            .replace("dakun", "大坤").replace("laobai", "老白").replace("luna", "Luna") \
            .replace("longname", "超级无敌长的主播名字用来试溢出")
        start = parts[0]["recorded"]
        if start.date() != now_bj().date():
            continue
        rec = anchor == "小美"
        t_today.append(dict(
            anchor=anchor, name=anchor,
            start_bj=fmt(start), end_bj="" if rec else fmt(start + datetime.timedelta(seconds=sum(p["dur"] for p in parts))),
            duration=sum(p["dur"] for p in parts), size=sum(p["size"] for p in parts),
            segments=sum(max(1, p["dur"] // 480) for p in parts), clips=sum(max(1, p["dur"] // 480) for p in parts),
            parts=len(parts), recording=rec, keep_forever=any(p.get("keep_forever") for p in parts),
            keep_priority=any(p.get("keep_priority") for p in parts),
            extended=False,
            expires_at=(now_bj().timestamp() + parts[0].get("left", 3 * 86400)),
        ))
    past = []
    for d, parts in SESSIONS:
        start = parts[0]["recorded"]
        if start.date() == now_bj().date():
            continue
        anchor = d.split("_")[-1].replace("xiaomei", "小美").replace("aze", "阿泽") \
            .replace("dakun", "大坤").replace("laobai", "老白").replace("luna", "Luna") \
            .replace("longname", "超级无敌长的主播名字用来试溢出")
        past.append(dict(
            anchor=anchor, name=anchor, start_bj=fmt(start),
            end_bj=fmt(start + datetime.timedelta(seconds=sum(p["dur"] for p in parts))),
            duration=sum(p["dur"] for p in parts), size=sum(p["size"] for p in parts),
            segments=sum(max(1, p["dur"] // 480) for p in parts), clips=sum(max(1, p["dur"] // 480) for p in parts),
            parts=len(parts), recording=False, keep_forever=False, keep_priority=False,
            extended=(anchor == "Luna"),
            expires_at=(now_bj().timestamp() + parts[0].get("left", 3 * 86400)),
        ))
    oneoff = [dict(name="临时-发布会", room_id="4477889", recording=True,
                   current=dict(start_bj=fmt(ago(minutes=42)), duration=2520, size=310_000_000,
                                segments=6, clips=6, parts=1),
                   live_checked_at=now_bj().timestamp())]
    jobs = {}
    for m in monitors():
        jobs[m["name"]] = dict(state=("running" if m.get("recording") else "idle"),
                               msg="" if m.get("recording") else "等待开播",
                               at=now_bj().timestamp())
    return dict(monitors=monitors(), oneoff=oneoff, today=t_today, past=past,
                now=now_bj().timestamp(), is_admin=True, keep_hours=72,
                jobs=jobs, owner_ids={"小美": 2, "阿泽": 2, "大坤": 3, "老白": 4,
                                      "Luna": 4, "超级无敌长的主播名字用来试溢出": 5})


def me():
    return dict(
        user=dict(id=1, account="ci", name="站长", email="ci@example.com", role="admin",
                  is_admin=True, disabled=False,
                  created_at=fmt(ago(hours=24 * 90)), last_login_at=fmt(ago(hours=1)),
                  expires_at=""),
        perms=dict(record=True, delete=True, files=True, users=True),
    )


def links():
    now = now_bj().timestamp()
    rows = [
        ("视频", "file", "发布会主视频.mp4", "发布会主视频", 1_240_000_000, 46, "发布会现场录像", "用户2"),
        ("视频", "file", "剪辑-花絮.mp4", "剪辑花絮", 380_000_000, 12, "", "用户2"),
        ("图片", "file", "封面-设计稿.png", "封面设计稿", 2_400_000, 30, "设计稿 v3", "用户3"),
        ("图片", "file", "直播截图合集.zip", "直播截图合集", 88_000_000, 5, "", "用户3"),
        ("文档", "file", "录制说明.txt", "录制说明", 12_000, 60, "使用说明", "用户4"),
        ("文档", "file", "已过期的合同.pdf", "已过期合同", 640_000, -30, "测试过期态", "用户4"),
        ("压缩包", "file", "全量素材.7z", "全量素材", 2_100_000_000, 72, "", "用户5"),
        ("外链", "link", "https://example.com/live", "外部回放地址", 0, 96, "外链不占空间", "用户5"),
        ("视频", "file", "已经不存在的文件.mp4", "已不存在", 500_000_000, 24, "测试「文件已不在服务器上」", "用户2"),
    ]
    out = []
    for i, (cat, kind, name, title, size, left_h, note, owner) in enumerate(rows, 1):
        out.append(dict(
            id="lk-%04d" % i, kind=kind, name=name, title=title, category=cat, size=size,
            expires_at=fmt(datetime.datetime.fromtimestamp(now + left_h * 3600, BJ)),
            expired=left_h < 0, added_at=fmt(ago(hours=3 * i)),
            owner=owner, share_code=("%04x" % (i * 7919)),
            download_url=("http://10.0.2.2:8090/media/sample.bin" if kind == "file" else ""),
            url=("https://example.com/live" if kind == "link" else "http://10.0.2.2:8090/preview/sample.txt"),
            previewable=(kind == "link"), exists=(i != 9),
            note=note,
        ))
    return out


def users():
    now = now_bj().timestamp()
    return dict(users=[
        dict(id=1, account="ci", name="站长", email="ci@example.com", role="admin", is_admin=True,
             disabled=False, created_at=fmt(ago(hours=24 * 90)), last_login_at=fmt(ago(hours=1)),
             perms=dict(record=True, delete=True, files=True, users=True)),
        dict(id=2, account="meimei", name="美美", email="meimei@example.com", role="user", is_admin=False,
             disabled=False, created_at=fmt(ago(hours=24 * 30)), last_login_at=fmt(ago(hours=5)),
             perms=dict(record=True, delete=True, files=True, users=False)),
        dict(id=3, account="aze", name="阿泽的号", email="", role="user", is_admin=False,
             disabled=False, created_at=fmt(ago(hours=24 * 12)), last_login_at=fmt(ago(hours=30)),
             perms=dict(record=True, delete=False, files=True, users=False)),
        dict(id=4, account="guest", name="访客", email="guest@example.com", role="user", is_admin=False,
             disabled=False, created_at=fmt(ago(hours=24 * 3)), last_login_at="",
             perms=dict(record=False, delete=False, files=True, users=False)),
        dict(id=5, account="old", name="停用的账号", email="old@example.com", role="user", is_admin=False,
             disabled=True, created_at=fmt(ago(hours=24 * 200)), last_login_at=fmt(ago(hours=24 * 60)),
             perms=dict(record=True, delete=True, files=True, users=False)),
    ], exp_presets={
        "1d": {"label": "1 天", "at": fmt(datetime.datetime.fromtimestamp(now + 86400, BJ)), "hours": 24},
        "7d": {"label": "7 天", "at": fmt(datetime.datetime.fromtimestamp(now + 7 * 86400, BJ)), "hours": 168},
        "30d": {"label": "30 天", "at": fmt(datetime.datetime.fromtimestamp(now + 30 * 86400, BJ)), "hours": 720},
        "90d": {"label": "90 天", "at": fmt(datetime.datetime.fromtimestamp(now + 90 * 86400, BJ)), "hours": 2160},
    })


def storage():
    rd_used = 41_200_000_000
    rd_total = 60_000_000_000
    sd_used = 27_400_000_000
    sd_total = 40_000_000_000
    return dict(
        ts=now_bj().timestamp(),
        record_disk=dict(used=rd_used, total=rd_total, free=rd_total - rd_used,
                         pct=round(rd_used * 100.0 / rd_total, 1), limit_pct=85.0, over_limit=False),
        sys_disk=dict(used=sd_used, total=sd_total, free=sd_total - sd_used,
                      pct=round(sd_used * 100.0 / sd_total, 1), over_limit=False),
        library=dict(
            by_anchor=[
                dict(anchor="小美", sessions=2, size=2_355_000_000, segments=52),
                dict(anchor="阿泽", sessions=1, size=1_590_000_000, segments=34),
                dict(anchor="大坤", sessions=1, size=1_180_000_000, segments=19),
                dict(anchor="超级无敌长的主播名字用来试溢出", sessions=1, size=2_450_000_000, segments=33),
            ],
            top=[
                dict(anchor="超级无敌长的主播名字用来试溢出", start_bj=fmt(ago(hours=2)),
                     end_bj=fmt(ago(hours=1.2)), size=2_450_000_000, segments=33),
                dict(anchor="小美", start_bj=fmt(ago(hours=3.5)), end_bj="",
                     size=1_510_000_000, segments=27),
                dict(anchor="大坤", start_bj=fmt(ago(hours=9.1)), end_bj=fmt(ago(hours=6.6)),
                     size=1_180_000_000, segments=19),
            ]),
        overflow=dict(over_limit=False, limit_pct=85.0, msg=""),
        policy=dict(keep_hours=72, priority_ratio=0.2, clean_at="04:00"),
        files=[
            dict(label="录制机日志", size=52_000_000),
            dict(label="上传缓存", size=8_400_000),
            dict(label="缩略图缓存", size=1_300_000),
        ],
    )


def history():
    out = []
    for i, (key, title, pos, dur) in enumerate([
        ("rec/x/live_p1.mp4", "小美 昨晚场次", 3120, 6480),
        ("rec/y/live_p1.mp4", "阿泽 今天第一段", 120, 4210),
        ("rec/z/live_p1.mp4", "大坤 今天场次", 8800, 9060),
        ("rec/w/live_p1.mp4", "Luna 前天场次", 2400, 2520),
        ("rec/v/live_p1.mp4", "（已删除的片源）", 60, 3300),
    ], 1):
        out.append(dict(key=key, title=title, position=pos, duration=dur,
                        watched_at=fmt(ago(hours=i * 5, minutes=i * 7))))
    return dict(history=out)


def announcements():
    return dict(announcements=[
        dict(title="服务端已升级到 v2 界面", body="客户端本次更新了底部四个入口与二级页，如遇异常请在群里反馈。",
             date=fmt(ago(hours=6))),
        dict(title="保留期调整为 72 小时", body="默认保留 72 小时；标注「优先保留」的场次不参与自动清理。",
             date=fmt(ago(hours=30))),
        dict(title="很长的公告标题用来测试换行与截断表现，看看会不会把卡片撑破",
             body="这是一条比较长的公告正文，用来检查公告抽屉与弹窗里的文字排版是否正常。",
             date=fmt(ago(hours=80))),
    ])


def update_json():
    return dict(versionCode=18, versionName="1.17", size=3343870, force=False,
                url="http://10.0.2.2:8090/app/lubo-1.17.apk",
                sha256="dac43e24" + "0" * 56, notes="CI 模拟更新信息")


# --------------------------------------------------------------------------- 验证码图(纯标准库 PNG)

def captcha_png(w=104, h=40, seed=7):
    rnd = random.Random(seed)
    rows = []
    for y in range(h):
        row = bytearray()
        for x in range(w):
            v = 235 - rnd.randint(0, 40)
            # 画几条“字符”竖条, 让它看起来像验证码
            for cx in (14, 34, 54, 74, 90):
                if abs(x - cx) <= 2 + (y // 8) % 2 and 6 < y < h - 6:
                    v = 40 + rnd.randint(0, 90)
            row += bytes((v, v, 255 if x % 3 else v))
        rows.append(bytes(row))
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    head = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


SAMPLE_BIN = b"luboku-ci-sample-payload\n" * 4096


# --------------------------------------------------------------------------- HTTP

class H(BaseHTTPRequestHandler):
    server_version = "luboku-ci/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, f, *a):
        pass

    # ---- 工具
    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=1), "application/json; charset=utf-8")

    def _authed(self):
        return SESS.split("=", 1)[1] in (self.headers.get("Cookie") or "")

    def _log(self, path, note=""):
        with LOCK:
            LOG.append("%s %s %s" % (now_bj().strftime("%H:%M:%S"), path, note))

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n).decode("utf-8", "replace") if n else ""

    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)
        self._log(p)
        try:
            self.route_get(p, q)
        except Exception as e:  # 别让 CI 因为一个接口挂掉
            self._json({"error": "ci-mock: %s" % e}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)
        body = self._body()
        form = {k: v[0] for k, v in parse_qs(body).items()}
        self._log(p, "form")
        try:
            self.route_post(p, q, form)
        except Exception as e:
            self._json({"error": "ci-mock: %s" % e}, 500)

    # ---- 路由
    def route_get(self, p, q):
        if p in ("/", "/index.html"):
            return self._send(200, "luboku ci mock\n", "text/plain; charset=utf-8")
        if p == "/__log":
            return self._send(200, "\n".join(LOG), "text/plain; charset=utf-8")
        if p == "/captcha.json":
            return self._json({"id": "ci-cap-1", "img": "/captcha.png?id=ci-cap-1"})
        if p.startswith("/captcha.png"):
            return self._send(200, captcha_png(), "image/png")
        if p == "/app/update.json":
            return self._json(update_json())
        if p == "/login":
            return self._send(200, LOGIN_HTML, "text/html; charset=utf-8")
        if p == "/logout":
            return self._send(302, "", "text/html", [("Set-Cookie", "lubo_sess=; Path=/; Max-Age=0")])
        if p.startswith("/media/") or p.startswith("/preview/"):
            return self._send(200, SAMPLE_BIN, "application/octet-stream")
        if p.startswith("/app/lubo-"):
            return self._send(200, b"placeholder-apk", "application/vnd.android.package-archive")

        # 以下都要登录态
        if not self._authed():
            return self._json({"error": "unauthorized"}, 401)
        if p == "/api/me.json":
            return self._json(me())
        if p == "/api/videos.json":
            return self._json(videos(all_=q.get("all", ["0"])[0] == "1"))
        if p == "/api/record/status.json":
            return self._json(record_status())
        if p == "/api/links.json":
            rows = links()
            owner = q.get("owner", [""])[0]
            if owner:
                rows = [r for r in rows if str(users()["users"][int(owner) - 1]["id"]) == owner]
            return self._json(rows)
        if p == "/api/users.json":
            return self._json(users())
        if p == "/api/site.json":
            return self._json({"site": dict(icp="冀ICP备2026000000号-1",
                                            icp_link="https://beian.miit.gov.cn/")})
        if p == "/api/admin/storage.json":
            return self._json(storage())
        if p == "/api/watch/history.json":
            return self._json(history())
        if p == "/api/announcements.json":
            return self._json(announcements())
        if p == "/api/stats.json":
            return self._json(dict(videos=len(videos()), sessions=len(SESSIONS),
                                   record=dict(running=1), files=dict(count=len(links()))))
        return self._json({"error": "no such path: %s" % p}, 404)

    def route_post(self, p, q, form):
        if p == "/login":
            account = (form.get("account") or "").strip()
            password = form.get("password") or ""
            if password == "wrong" or account == "bad":
                return self._send(401, LOGIN_HTML.replace(
                    "<div class=\"err\">(占位)</div>",
                    "<div class=\"err\">账号或密码不正确，还可以尝试 5 次</div>"),
                    "text/html; charset=utf-8")
            return self._send(302, "", "text/html; charset=utf-8",
                              [("Set-Cookie", SESS + "; Path=/; Max-Age=2592000"), ("Location", "/")])
        if not self._authed():
            return self._json({"error": "unauthorized"}, 401)
        if p == "/api/record/act":
            return self._json({"ok": True, "msg": "CI 模拟: 已执行 " + str(form.get("action"))})
        if p == "/api/users/act":
            return self._json({"ok": True, "msg": "CI 模拟: 已保存(不落库)"})
        if p == "/api/site/act":
            return self._json({"ok": True, "msg": "CI 模拟: 站点设置已保存"})
        if p == "/api/links/expire":
            return self._json({"ok": True, "msg": "CI 模拟: 有效期已更新"})
        if p == "/api/links/delete":
            return self._json({"ok": True, "msg": "CI 模拟: 已删除"})
        if p == "/api/upload":
            return self._json({"ok": True, "msg": "CI 模拟: 上传完成", "id": "lk-ci-new"})
        if p == "/api/watch/act":
            return self._json({"ok": True, "msg": "CI 模拟: 观看记录已更新"})
        if p == "/api/me/password":
            return self._json({"ok": True, "msg": "CI 模拟: 密码已修改"})
        return self._json({"error": "no such path: %s" % p}, 404)


LOGIN_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>录播库 · 登录</title></head>
<body><h1>录播库</h1>
<div class="err">(占位)</div>
<p>这是 CI 模拟服务端的登录页（App 只在登录失败时从这里抠 &lt;div class="err"&gt; 的文案）。</p>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print("luboku ci mock listening on http://%s:%d  session=%s" % (a.host, a.port, SESS), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
