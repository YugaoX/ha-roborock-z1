# 石头 Z1 Max · Home Assistant 自定义集成

让 Roborock App 中的 **Z1 Max 洗衣机和独立干衣机**接入 Home Assistant：查看状态、启动当前程序、接收程序完成提醒。

这是社区项目，与石头科技和 Home Assistant 官方无隶属关系。当前界面以中文为主。

## 支持范围

| 设备 | 精确型号 | 已验证能力 |
| --- | --- | --- |
| Z1 Max 洗衣机 | `roborock.wm.a180` | 状态、故障、启动、自然结束通知 |
| Z1 Max 分子筛干衣机 | `roborock.cd.a188` | 状态、故障、启动、丝绸护理自然结束信号 |

实测环境：**Home Assistant 2026.2.3、python-roborock 4.8.0、ARM64 Linux**。依赖版本固定，**不承诺兼容更新的 HA 或 SDK**；较新 HA 的内置 Roborock 可能要求不同 SDK，请先核对，勿强制降级共享依赖。其他型号和全部洗护程序尚未验证。

## 安装

### HACS 自定义仓库

1. 在 HACS 的“自定义存储库”添加 `https://github.com/MXHRUI/ha-roborock-z1`，类型选择 **Integration / 集成**。
2. 下载集成并重启 Home Assistant。
3. 按下面的“配置账号”完成配置。

本仓库按 [HACS 自定义集成结构](https://www.hacs.xyz/docs/publish/integration/)提供文件，尚未加入 HACS 默认商店，也未宣称获得 HACS 官方审核。

### 手动安装

从 [Releases](https://github.com/MXHRUI/ha-roborock-z1/releases) 下载 `roborock_z1_monitor.zip`，解压后把其中的 `custom_components/roborock_z1_monitor` 放到 HA 配置目录，最终应能看到：

```text
<HA配置目录>/custom_components/roborock_z1_monitor/manifest.json
```

重启 HA。不要把整个仓库放进 `custom_components`，也不要在运行中覆盖内置 Roborock 或共享 SDK 文件。

## 配置账号

1. 两台设备先在 **Roborock App** 正常绑定并在线。
2. 在 HA“设置 → 设备与服务”添加内置 **Roborock**，完成账号登录。本集成复用这个账号条目，不另存一份账号密码。
3. 添加本集成 **石头 Z1 Max**，选择已有 Roborock 账号。
4. 即使内置集成提示没有受支持的设备，只要账号条目已成功保留，本集成仍可使用它。只含这两台设备时，可以禁用该内置条目的运行，但**不要删除账号条目**；若其中还有扫地机等设备，不要随意禁用。

如果内置登录没有生成账号条目，本集成无法绕过登录。若授权过期，需在原 Roborock 集成中重新认证。提交问题时请说明 HA 和 SDK 版本及错误类型，不要提交账号、令牌或完整诊断包。

## 使用

每台设备提供状态、程序时间、故障码、通信状态、启动当前程序按钮、完成提醒开关和测试提醒按钮。

- **启动**：先在 Roborock App 选择程序、准备衣物并关好门，再按 HA 启动按钮。仅在实时确认待机且无故障时发送；模式、程序、转速与启动在同一条消息中提交。60 秒内不重复发送，超时不会自动重试。
- **完成提醒**：显示在 HA 左侧“通知”。订阅实时结束信号，避免几秒钟的完成状态被每分钟轮询漏过。取消、单独待机、故障或离线不会直接当成完成。
- **时间**：干衣机待机时显示所选程序预计时长，不代表正在运行。洗衣机保留原始时间读数，不对全部程序的单位作保证。
- **测试提醒**：仅创建明确标记的测试通知，不启动电器，也不触发下面的语音蓝图。
- **暂停/取消/其他参数**：请使用 Roborock App。界面状态约每分钟更新，完成通知可能先于界面状态刷新。

## 可选：两块屏同时播报，凌晨静音

仓库包含 [完成语音提醒蓝图](blueprints/automation/z1_completion_voice.yaml)。在 HA“设置 → 自动化与场景 → 蓝图 → 导入蓝图”粘贴：

```text
https://github.com/MXHRUI/ha-roborock-z1/blob/main/blueprints/automation/z1_completion_voice.yaml
```

创建自动化时选择两块中控屏的 **播放文本** `notify` 实体（不是“执行文本指令”）。默认按 HA 本地时区 **00:00–06:00 静音，06:00 后恢复，夜间结束不补播**。两路并行发送，保持现有音量；网络和设备处理可能带来少量起播差异。关闭本集成的完成提醒开关也会停止对应的语音触发。

蓝图基于已经实际听音验证的双屏自动化，导入时需选择自己的设备。它不要求本项目读取你的小米账号；播放文本实体由 Xiaomi Home 等集成提供。通用 notify 实体未必支持语音，请选择确实能播报的实体。

## 验证与限制

- 基线 0.2.1 已实机验证两台启动、无故障短程序自然结束；洗衣机追加约 86 秒短周期后，HA 实际生成一条完成通知。
- 干衣机 10 分钟护理的自然结束信号已实测并回放校准；未再次运行新版干衣机完整周期来验证通知。
- 仓库的离线测试覆盖启动字段、重复启动保护、超时不重试、瞬时完成、取消、故障、过期数据和通知开关，不会操作真实设备。
- 依赖云端账号及网络。HA 停机或网络中断期间不能保证补发完成提醒。仅认定明确结束信号，不以时间归零推断完成。
- 当前初始化检查 SDK 版本时可能记录事件循环阻塞警告；这是已知问题。升级 SDK 前需要重新适配，本版本明确锁定 4.8.0。

运行测试：`python -m unittest discover -s tests -v`。

## 反馈与许可

请在 [Issues](https://github.com/MXHRUI/ha-roborock-z1/issues) 提供设备型号、HA 版本和已脱敏的错误信息。不得上传 `.storage`、令牌、家庭设备清单或配置备份。

采用 [GNU GPL v3](LICENSE)。认证、消息编码和传输使用 [Python-roborock/python-roborock](https://github.com/Python-roborock/python-roborock)；本项目不修改其共享类，也不把干衣机伪装为洗衣机。参见 [第三方说明](NOTICE.md)。
