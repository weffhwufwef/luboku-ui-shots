# 页面走查报告

| 步骤 | 结果 | 说明 |
|---|---|---|
| prepare | ✅ | Physical size: 1080x2340 / Physical density: 440 |
| 设置服务端地址(长按品牌块) | ✅ | 已切到 http://10.0.2.2:8090 |
| shot:01_login_normal | ✅ | 152443 bytes |
| shot:02_login_error | ✅ | 139622 bytes |
| 登录(正常) → 录播库 | ✅ | .MainActivity |
| shot:03_lib_top | ✅ | 335112 bytes |
| shot:04_lib_scrolled | ✅ | 272928 bytes |
| shot:05_announce_sheet | ✅ | 319973 bytes |
| shot:06_announce_dialog | ✅ | 319051 bytes |
| 全部主播 | ❌ | 第1次: 找不到入口(位 · 全部) |
| shot:07_streamers_FAIL | ✅ | 309566 bytes |
| 主播详情 | ❌ | 点了主播卡没进 StreamerActivity: .MainActivity |
| shot:09_streamer_FAIL | ✅ | 309566 bytes |
| shot:11_player_portrait | ✅ | 237940 bytes |
| shot:11g_player_paused | ✅ | 229378 bytes |
| shot:11b_player_seg2 | ✅ | 231433 bytes |
| 播放器全屏按钮 | ❌ | 找不到 fs |
| shot:11f_player_live | ✅ | 184774 bytes |
| tab1 → RecordActivity | ❌ | 底边=-140, 点了 10 个坐标 + am start 都没进, 当前=.MainActivity |
| shot:12_record_top_FAIL | ✅ | 309912 bytes |
| tab2 → MeActivity | ❌ | 底边=-140, 点了 10 个坐标 + am start 都没进, 当前=.MainActivity |
| shot:16_me_top_FAIL | ✅ | 309712 bytes |
| 我的 Tab | ❌ | 不在 MeActivity: .MainActivity |
| tab0 → MainActivity | ✅ | 点击 (180,-219) |
| shot:27_search_empty | ✅ | 93287 bytes |
| shot:28_search_results | ✅ | 136227 bytes |

logcat 可疑行: 1404（见 logcat_errors.txt）

## 服务端收到的请求
```
00:56:02 / 
00:56:02 /captcha.json 
00:58:09 /login 
00:58:09 /captcha.json 
00:58:09 /captcha.png 
00:59:18 /login form
00:59:18 /captcha.json 
00:59:18 /captcha.png 
00:59:18 /login 
01:00:08 /login form
01:00:08 /api/me.json 
01:00:08 /app/update.json 
01:00:08 /api/videos.json 
01:00:09 /api/record/status.json 
01:00:09 /api/watch/history.json 
01:00:09 /api/announcements.json 
01:00:09 /thumb/live_p3.mp4.jpg 
01:00:09 /api/announcements.json 
01:00:09 /thumb/live.m3u8.jpg 
01:00:09 /thumb/live_p1.mp4.jpg 
01:00:09 /thumb/live_p1.mp4.jpg 
01:00:09 /thumb/live_p2.mp4.jpg 
01:00:09 /thumb/live_p1.mp4.jpg 
01:00:11 /api/record/status.json 
01:00:11 /media/avatar/%E5%B0%8F%E7%BE%8E.jpg 
01:00:11 /media/avatar/%E9%98%BF%E6%B3%BD.jpg 
01:00:11 /media/avatar/%E5%A4%A7%E5%9D%A4.jpg 
01:00:11 /media/avatar/%E8%80%81%E7%99%BD.jpg 
01:00:11 /media/avatar/Luna.jpg 
01:00:11 /media/avatar/%E8%B6%85%E7%BA%A7%E6%97%A0%E6%95%8C%E9%95%BF%E7%9A%84%E4%B8%BB%E6%92%AD%E5%90%8D%E5%AD%97%E7%94%A8%E6%9D%A5%E8%AF%95%E6%BA%A2%E5%87%BA.jpg 
01:00:17 /api/videos.json 
01:00:17 /api/record/status.json 
01:00:17 /api/watch/history.json 
01:00:24 /api/videos.json 
01:00:24 /api/record/status.json 
01:00:24 /api/watch/history.json 
01:00:26 /api/videos.json 
01:00:26 /api/record/status.json 
01:00:26 /api/watch/history.json 
01:00:28 /api/videos.json 
01:00:28 /api/record/status.json 
01:00:28 /api/watch/history.json 
01:00:28 /api/videos.json 
01:00:28 /api/record/status.json 
01:00:29 /api/watch/history.json 
01:00:31 /api/announcements.json 
01:00:38 /api/announcements.json 
01:00:48 /api/videos.json 
01:00:48 /api/record/status.json 
01:00:48 /api/watch/history.json 
01:00:54 /media/live_p1.mp4 
01:01:06 /media/live_p2.mp4 
01:01:09 /api/watch/act form
01:01:18 /media/live_p3.mp4 
01:01:24 /api/watch/act form
01:01:25 /media/live_p2.mp4 
01:01:35 /api/watch/act form
01:01:35 /api/videos.json 
01:01:35 /api/record/status.json 
01:01:35 /api/watch/history.json 
01:01:35 /api/announcements.json 
01:01:38 /media/live.m3u8 
01:01:46 /api/videos.json 
01:01:46 /api/record/status.json 
01:01:46 /api/watch/history.json 
01:01:46 /api/announcements.json 
01:02:06 /api/videos.json 
01:02:06 /api/record/status.json 
01:02:06 /api/watch/history.json 
01:02:26 /api/videos.json 
01:02:26 /api/record/status.json 
01:02:26 /api/watch/history.json 
01:02:46 /api/videos.json 
01:02:46 /api/record/status.json 
01:02:46 /api/watch/history.json 
01:03:06 /api/videos.json 
01:03:06 /api/record/status.json 
01:03:06 /api/watch/history.json 
01:03:26 /api/videos.json 
01:03:26 /api/record/status.json 
01:03:26 /api/watch/history.json 
01:03:46 /api/videos.json 
01:03:46 /api/record/status.json 
01:03:46 /api/watch/history.json 
01:04:06 /api/videos.json 
01:04:06 /api/record/status.json 
01:04:06 /api/watch/history.json 
01:04:26 /api/videos.json 
01:04:26 /api/record/status.json 
01:04:26 /api/watch/history.json 
01:04:46 /api/videos.json 
01:04:46 /api/record/status.json 
01:04:46 /api/watch/history.json 
01:05:06 /api/videos.json 
01:05:06 /api/record/status.json 
01:05:06 /api/watch/history.json 
01:05:26 /api/videos.json 
01:05:26 /api/record/status.json 
01:05:26 /api/watch/history.json 
01:05:46 /api/videos.json 
01:05:46 /api/record/status.json 
01:05:46 /api/watch/history.json 
01:06:06 /api/videos.json 
01:06:06 /api/record/status.json 
01:06:06 /api/watch/history.json 
01:06:26 /api/videos.json 
01:06:26 /api/record/status.json 
01:06:26 /api/watch/history.json 
01:06:46 /api/videos.json 
01:06:46 /api/record/status.json 
01:06:46 /api/watch/history.json 
01:07:06 /api/videos.json 
01:07:06 /api/record/status.json 
01:07:06 /api/watch/history.json 
01:07:26 /api/videos.json 
01:07:26 /api/record/status.json 
01:07:26 /api/watch/history.json 
01:07:46 /api/videos.json 
01:07:46 /api/record/status.json 
01:07:46 /api/watch/history.json 
01:08:06 /api/videos.json 
01:08:06 /api/record/status.json 
01:08:06 /api/watch/history.json 
01:08:26 /api/videos.json 
01:08:26 /api/record/status.json 
01:08:26 /api/watch/history.json 
01:08:46 /api/videos.json 
01:08:46 /api/record/status.json 
01:08:46 /api/watch/history.json 
01:09:06 /api/videos.json 
01:09:06 /api/record/status.json 
01:09:06 /api/watch/history.json 
01:09:26 /api/videos.json 
01:09:26 /api/record/status.json 
01:09:26 /api/watch/history.json 
01:09:46 /api/videos.json 
01:09:46 /api/record/status.json 
01:09:46 /api/watch/history.json 
01:10:06 /api/videos.json 
01:10:06 /api/record/status.json 
01:10:06 /api/watch/history.json 
01:10:26 /api/videos.json 
01:10:26 /api/record/status.json 
01:10:26 /api/watch/history.json 
01:10:46 /api/videos.json 
01:10:46 /api/record/status.json 
01:10:46 /api/watch/history.json 
01:11:06 /api/videos.json 
01:11:06 /api/record/status.json 
01:11:06 /api/watch/history.json 
01:11:26 /api/videos.json 
01:11:26 /api/record/status.json 
01:11:26 /api/watch/history.json 
01:11:46 /api/videos.json 
01:11:46 /api/record/status.json 
01:11:46 /api/watch/history.json 
01:12:06 /api/videos.json 
01:12:06 /api/record/status.json 
01:12:06 /api/watch/history.json 
01:12:26 /api/videos.json 
01:12:26 /api/record/status.json 
01:12:26 /api/watch/history.json 
01:12:46 /api/videos.json 
01:12:46 /api/record/status.json 
01:12:46 /api/watch/history.json 
01:13:06 /api/videos.json 
01:13:06 /api/record/status.json 
01:13:06 /api/watch/history.json 
01:13:26 /api/videos.json 
01:13:26 /api/record/status.json 
01:13:26 /api/watch/history.json 
01:13:46 /api/videos.json 
01:13:46 /api/record/status.json 
01:13:46 /api/watch/history.json 
01:14:06 /api/videos.json 
01:14:06 /api/record/status.json 
01:14:06 /api/watch/history.json 
01:14:26 /api/videos.json 
01:14:26 /api/record/status.json 
01:14:26 /api/watch/history.json 
01:14:46 /api/videos.json 
01:14:46 /api/record/status.json 
01:14:46 /api/watch/history.json 
01:15:06 /api/videos.json 
01:15:06 /api/record/status.json 
01:15:06 /api/watch/history.json 
01:15:26 /api/videos.json 
01:15:26 /api
```