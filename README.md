# luboku-ui-shots — 录播库 App 的「模拟器自动走查」流水线

这个仓库不放业务代码，只做一件事：**在 GitHub 的 macOS runner 上跑一个硬件加速的安卓模拟器，
装上录播库 APK，配一个 CI 模拟服务端，然后把 App 的每个页面点一遍并截图。**

## 为什么是 macOS runner

- GitHub 托管的 Linux runner **不给 `/dev/kvm`**（官方 issue 说明：runner 本身就是 Azure 上的 VM，
  安全策略不允许嵌套虚拟化），只有付费 larger runner 才开。
- GitHub 的 macOS runner 跑在**真 Mac** 上，有 Hypervisor.framework，所以
  `ReactiveCircus/android-emulator-runner` 能在上面跑**硬件加速**的安卓模拟器 —— 公共仓库免费不限分钟。

## 组成

| 文件 | 作用 |
|---|---|
| `mock/server.py` | CI 模拟服务端（Python 标准库）：把 `ApiClient.java` 里用到的每个接口按客户端的解析口径返回一份形状正确、内容可控的数据；时间字段相对当前时刻动态生成，所以永远有「今日」场次。 |
| `ci/drive.py` | 走查脚本：`uiautomator dump` 读层级 → 按 resource-id / 文案点控件 → `screencap` 截图；顺带收 logcat 和每页层级 XML。 |
| `.github/workflows/shots.yml` | 流水线：起 mock → 跑模拟器 → 装 APK → 走查 → 截图提交回仓库。 |
| `app/lubo-1.17.apk` | 被测的客户端包（与 `http://47.122.106.244/app/` 上发布的一致）。 |
| `shots/` | 产物：每页截图 + 该页层级 XML + `report.md` + `logcat_errors.txt`。 |

## 怎么重跑

改 `app/` 里的 APK 后 `git push`，或者到 Actions 页面点 **Run workflow**（可以指定 APK 路径）。
跑完截图会被提交到 `shots/`，直接 `raw.githubusercontent.com` 就能看，不需要 token。

## 注意

- 模拟服务端只用于 UI 走查：**不落库、不做鉴权**（任意密码都放行，只有 `password=wrong` 用来截「登录失败」态）。
- 播放器页面的视频是占位文件，能验证播放器界面，不能验证真实播放。
