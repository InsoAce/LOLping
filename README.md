# LOLping · 海克斯传讯

![License: MIT](https://img.shields.io/badge/license-MIT-c5a566)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-59d4df)

A Hextech-inspired Windows overlay for sharing a teammate's selected champion in League of Legends champion-select chat.

在英雄联盟选人界面显示五个独立楼层按钮。点击对应楼层，只发送该玩家当前英雄的一条普通聊天消息：

```text
1楼 (寒冰射手) - 存活
```

## 使用

1. 双击 `dist/LOLping.exe`，在 Windows 权限提示中确认，以便读取管理员权限客户端的本地连接参数。程序默认在系统托盘运行，不弹设置窗。
2. 右键托盘中的海克斯水晶图标，选择“设置 / 连接状态”检查连接。未连接时，可以选择 `LeagueClient/lockfile`；国服 lockfile 可能为空，或客户端以管理员身份运行，这时点击“管理员重连”，由 Windows 显示权限提示。
3. 进入选人阶段，五个楼层按钮自动出现。点击对应楼层发送一条消息。未选英雄的按钮不可用，预选英雄也可发送。鼠标移到按钮上，可在设置窗查看消息预览。
4. 没有单次发送间隔限制。连续发送四条后冷却两秒，停发两秒也会重置计数；按钮显示倒计时。每次点击只发送一条，不会自动连发。

楼层按钮跟随客户端移动、缩放；离开选人阶段、最小化客户端或切换到其他程序时隐藏。设置窗默认隐藏，只在通过托盘手动打开时显示。关闭设置窗会收起到托盘；退出程序请右键托盘选择“退出”。

首次使用可在选人阶段通过托盘打开设置，勾选“校准位置”，拖动五个按钮到各楼层旁，再取消勾选保存。校准时不发送消息。默认位置依据标准选人布局，其他模式需要调整；“重置位置”恢复默认位置。

“存活”为固定文本，并非检测到的游戏内生命状态。只读取本方选人数据，不查询匿名玩家真实姓名。发送前重新检查楼层、英雄和房间，发生变化时取消此次发送。网络发送失败不会自动重试，应先检查聊天框再决定是否重发。

## 开发与演示

Windows / Python 3.8+（需要 Tkinter），创建隔离环境并安装依赖后运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe overlay.py
.\.venv\Scripts\python.exe overlay.py --demo
.\.venv\Scripts\python.exe -m unittest -v
```

演示模式使用样例数据，可在大厅或无客户端时展示按钮；点击只更新本地提示，不连接或发送真实聊天消息。日常使用请直接双击 exe，不要添加 `--demo`。

打包（开发环境安装 PyInstaller 6.11.1）：

```powershell
.\.venv\Scripts\python.exe -m pip install PyInstaller==6.11.1
.\build.ps1
```

`app.py` 实现后台读写；`lcu.py` 实现本地传输、楼层解析和冷却规则；`overlay.py` 实现托盘、设置窗和独立悬浮按钮。

海克斯主题采用深海蓝底、古铜金切角边框、楼层菱形徽记和青蓝悬停高光。冷却时显示倒计时与进度条，未选英雄时降低亮度。`hextech.py` 使用 Canvas 绘制界面与图标，跟随窗口尺寸缩放。`python preview_ui.py` 可打开完全离线的设置窗与按钮样式预览，不连接客户端。

使用接口：`/lol-gameflow/v1/gameflow-phase`、`/lol-champ-select/v1/session`、`/lol-chat/v1/conversations`、`/lol-chat/v1/conversations/{id}/messages` 和客户端英雄数据。内置中文英雄名称来自 Riot Data Dragon，版本和来源见 `champions_source.json`。

用户选择的 lockfile 路径保存在 `%APPDATA%/LoLQuickChat/settings.json`；按钮位置保存在同目录的 `positions.json`。连接令牌只保留在内存中。

LCU 是客户端内部接口，Riot 不保证第三方支持或兼容性。此程序未获官方审核，不承诺账号风险为零。参考 [LCU 官方说明](https://developer.riotgames.com/docs/lol#league-client-api) 和 [第三方工具规则](https://support.riotgames.com/en-us/riot/events/third-party-applications)。

## 项目状态与许可证

当前为早期原型。15 项单元测试及离线界面检查已通过，尚未完成真实聊天室发送和跨电脑兼容性验证。发现问题时，请提供客户端阶段、Windows 显示缩放和托盘连接状态；请勿上传 lockfile、连接令牌或账号信息。

原创代码及美术采用 [MIT License](LICENSE)。游戏名称和英雄数据的权利归 Riot Games 所有，见 [NOTICE](NOTICE)。
