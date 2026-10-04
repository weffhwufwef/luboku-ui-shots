#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 uiautomator 层级做「卡片贴边 / 缩进不一致」审计。

用法: python3 ci/audit.py shots-ci2 [页面前缀...]
口径: 1080x2340 @440dpi → 1dp = 2.75px; 设计稿页面 gutter = 24dp = 66px, 右边界 1014。

判定:
  · 叶子节点(有文字/图标)左边界 < 30px  → 贴边(整行铺满的跳过)
  · 输出卡片内文字左边界, 用来发现「卡片内边距不统一」
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

DPI = 2.75
GUTTER_PX = 66
EDGE = 30


def bx(n):
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.attrib.get("bounds", ""))
    return tuple(int(x) for x in m.groups()) if m else None


def audit(path):
    try:
        t = ET.parse(path)
    except Exception as e:
        print("  ! 解析失败 %s" % e)
        return
    print("### %s" % os.path.basename(path))
    bad = []
    for n in t.iter("node"):
        txt = (n.attrib.get("text") or "").strip()
        desc = (n.attrib.get("content-desc") or "").strip()
        cls = (n.attrib.get("class") or "").split(".")[-1]
        rid = (n.attrib.get("resource-id") or "").split("/")[-1]
        if not (txt or desc) or cls in ("FrameLayout", "LinearLayout", "ScrollView"):
            continue
        b = bx(n)
        if not b:
            continue
        l, tp, r, bo = b
        if r - l <= 0 or bo - tp <= 0:
            continue                      # 被裁剪/0 尺寸的节点不可信, 跳过
        if l < EDGE and r > 1080 - EDGE:
            continue                      # 整行铺满(背景/分隔行)
        # 横向多列统计行: 每列是等宽 TextView、文字居中 → 左边界自然是 0, 不是贴边
        pa = par.get(n)
        if pa is not None:
            kids = [k for k in list(pa) if bx(k)]
            if len(kids) >= 2:
                widths = [bx(k)[2] - bx(k)[0] for k in kids]
                if all(w >= 200 for w in widths) and abs(sum(widths) - 1080) < 40:
                    continue
        if l < EDGE or (0 < GUTTER_PX - l < 12):
            bad.append((rid or cls, txt[:16] or desc[:16], l, tp))
    if bad:
        print("  贴边元素(左边界 < 30px):")
        for rid, txt, l, tp in bad:
            print("    %-14s %-18s x=%4d px (%.1f dp)  y=%d" % (rid, txt, l, l / DPI, tp))
    else:
        print("  ✓ 没有贴边元素")
    insets = {}
    for n in t.iter("node"):
        rid = (n.attrib.get("resource-id") or "").split("/")[-1]
        if rid in ("title", "sub", "arName", "arSub", "acName", "acSub", "fhName", "fhSub"):
            b = bx(n)
            if b and b[2] > b[0] and b[3] > b[1]:
                insets.setdefault(rid, set()).add(b[0])
    if insets:
        print("  卡片内文字左边界: " + "  ".join("%s=%s" % (k, sorted(v)) for k, v in insets.items()))


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "shots"
    pref = sys.argv[2:]
    if not os.path.isdir(d):
        print("目录不存在: %s" % d)
        return
    files = sorted(f for f in os.listdir(d) if f.endswith(".xml") and not f.startswith("_"))
    if pref:
        files = [f for f in files if any(f.startswith(p) for p in pref)]
    for f in files:
        audit(os.path.join(d, f))
        print()


if __name__ == "__main__":
    main()
