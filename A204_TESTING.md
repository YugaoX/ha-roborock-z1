# a204 实验性支持：测试与回滚

## 修改范围

- 基于上游提交 `e316e348d79157a108709a94a76d1533cca1d3da`，分支 `add-a204-support`。
- 在 `protocol.py` 的 `MODELS` 加入精确型号 `roborock.wm.a204`。
- 诊断版 0.2.2 在 `client.py` 记录设备发现过程，并在线程中读取 SDK 版本，
  避免原来的 `listdir/read_text/open` 阻塞警告；SDK 4.8.0 检查仍在任何发现请求前执行。
- 保留所有协议、schema、响应值及启动保护；没有 SDK 适配、共享依赖修改或 SDK 版本升级。
- 测试使用合成 schema 与模拟传输，不是 a204 实机记录，也未连接真实设备。

## 保留的校验与限制

| 检查 | 现有要求 |
| --- | --- |
| 设备协议 | `pv` 必须精确等于 `A01` |
| 只读字段 | `203/status`、`218/washing_left`、`220/error` 均为 `ro` + `VALUE` |
| 查询 | `10000` 的 `code` 为 `id_query`；原实现未校验该字段的类型与读写属性 |
| 响应 | 三个只读值均为非负整数；不接受布尔值或用零替代缺失值 |
| 可选启动 | `200/start` 为 `rw` + `BOOL`，`204/mode`、`205/program`、`209/spin_level` 为 `rw` + `VALUE` |
| 启动前 | 重新查询；状态为 1、故障为 0、三个程序参数均为正整数 |
| 启动发送 | 参数与启动同包发送，60 秒防重复，超时不自动重试 |

只读 schema 不符或协议不是 A01 时，保留原实现的初始化失败行为，可能影响同一账号下
本自定义集成的其他设备；不会悄悄跳过校验。只有控制 schema 不符时仍可只读接入，
启动按钮不可用。schema 相同不能证明 a204 的数值语义相同。

`client.py` 仍硬性要求 `python-roborock==4.8.0`，`manifest.json` 也固定此依赖，
打包脚本继续校验该版本。上游仅实测 HA 2026.2.3 / SDK 4.8.0。
**若当前 HA（例如先前提及的 2026.9.2）要求 SDK 7.4.2，请不要直接安装或强制降级共享依赖。**
本补丁不解决新版 SDK 兼容问题；先使用隔离的兼容测试环境，或另行适配新版 SDK。

## HACS / 自定义仓库安装

1. 备份 HA 配置与现有 `custom_components/roborock_z1_monitor`，记录 HA、SDK 版本。
   确认测试环境可使用 SDK 4.8.0，设备已在 Roborock App 绑定并在线。
2. 在 HACS → 自定义存储库，填入此次 **Fork 仓库根地址** `https://github.com/YugaoX/ha-roborock-z1`，类型选 Integration。
   不要填上游地址或 `/tree/add-a204-support` 页面地址。
3. 必须安装包含本次提交的版本。若 HACS 只显示默认分支/已发布版本而没有测试分支，
   使用下面的手动安装方法；不要将上游 `main` 误当成 a204 测试版。
4. 手动安装：在 Fork 的 GitHub 页面切到 `add-a204-support` → Code → Download ZIP。
   解压，将其中 `custom_components/roborock_z1_monitor` 放入 HA 配置目录。
   或使用随本次修改提供的组件安装 ZIP。最终路径应为
   `<HA配置目录>/custom_components/roborock_z1_monitor/manifest.json`。
   不要嵌套整个仓库目录；不要覆盖内置 Roborock 或 SDK。
5. 检查安装目录的 `protocol.py` 包含 `roborock.wm.a204`，再重启 HA。
   诊断版 manifest 版本为 `0.2.2`，且 `client.py` 包含 `a204-diagnostics-1`。
6. 在“设置 → 设备与服务”完成内置 Roborock 账号认证并保留账号条目，
   添加“石头 Z1 Max”并选择此账号。已配置过本自定义集成时，重启后验证原条目即可。

## 分阶段实机测试

1. **先只读**：不要按 HA 的启动按钮，也不要把它接入自动化。
   关闭 a204 的“完成提醒”开关；当前完成判断仍沿用 a180/a188 的数值规则，
   a204 尚未验证，不能据此确认程序已完成。
2. 检查 a180 原有实体正常，a204 出现状态、程序时间原始值、故障码、通信状态。
   对照 App 记录待机、运行、自然结束各阶段的 `203/218/220` 数值；常规刷新约一分钟。
   a204 显示“状态码 N”是预期行为，未套用 a180 的状态名称或时间单位。
3. 如果 schema 或 A01 校验失败，停止本轮测试并回滚。记录脱敏错误、完整型号、
   HA/SDK 版本；必要时仅提供相关 DPS 的 id/code/mode/type，勿提供账号、令牌、
   设备 ID、`.storage`、家庭清单或完整诊断包。
4. **可选控制**：仅在确认 a204 的待机码 1、无故障码 0 和程序参数语义一致后，
   才考虑人工测试原有启动路径。先在 App 选择程序、准备衣物、关门，现场观察，
   HA 只按一次启动。按钮不可用时不要绕过 schema；超时先查 App，勿立即重复启动。
5. a204 的完整周期与完成提醒需要另行对照实机验证后再启用。

## 回滚

- 恢复备份的 `custom_components/roborock_z1_monitor` 后重启 HA；或安装上游原版。
  不删除内置 Roborock 的账号条目。
- 代码层面可撤销添加 a204 白名单的功能提交以停止发现 a204；完整回滚时，按从新到旧的顺序撤销本分支的文档、测试与功能提交。
- HACS 后续下载默认分支或更新可能覆盖测试补丁；更新前核对分支与 `protocol.py`。

## 离线验证

使用 Python 3.11 或更新版本运行（上游 CI 为 3.13）：

```sh
python -m unittest discover -s tests -v
python scripts/build_release.py
```

新增测试覆盖 a204 精确型号、缺失/变更只读字段、查询字段、原始响应保留，
以及控制字段不符时禁止启动但仍接受只读 schema。现有启动测试也会遍历 a204。
离线通过不等同于 HA / SDK 联调或实机兼容通过。

## 0.2.2 从头安装与发现日志

Fork 的默认 `main` 目前仍是原版，没有 a204；不要仅添加 Fork 根地址后直接安装默认版。
本轮优先使用诊断 ZIP 手动安装，避免 HACS 默认分支或缓存影响结果。

1. 确认 HA 当前版本和内置 Roborock 的 SDK 要求。旧日志读取到 4.8.0 元数据，
   只能证明当时读到了该版本；不能证明当前更新后的 HA 依赖仍兼容。
2. 备份现有配置；将 ZIP 中的 `custom_components/roborock_z1_monitor` 放入 HA
   配置目录。确认 manifest 为 0.2.2、protocol 包含完整型号、client 包含诊断标记。
3. 在 `configuration.yaml` 现有 `logger.logs` 中加入下面一项；没有 logger 时使用完整示例。
   同一文件不要重复建立顶层 `logger:`。这仅开启本组件的 info 日志，不要开启 SDK/HTTP 的全量调试。

```yaml
logger:
  default: warning
  logs:
    custom_components.roborock_z1_monitor: info
```

4. 重启 HA；在设备与服务中保留或添加内置 Roborock 账号，选择与 App 中 a204 相同的账号。
   添加“石头 Z1 Max”，选择此账号。设备自动发现，没有单独的 a204 添加步骤。
5. 打开“设置 → 系统 → 日志”，显示原始日志，搜索 `Z1 discovery`。
   将这些行和相关 `Z1 monitor setup failed` 错误发来，另提供 HA 当前版本。
   诊断日志只记录模型、协议、计数、相关 schema 定义、SDK 版本与控制能力；
   不主动记录账号、令牌、设备 ID、家庭 ID、设备名称或完整云端响应。
6. 初次测试关闭 a204 完成提醒，不按启动；用 App 开始程序后对照只读数值。

| 日志 | 下一步判断 |
| --- | --- |
| 没有 `build=a204-diagnostics-1` | 核对 info 日志设置、安装路径、是否重启及是否添加此集成 |
| `skipped model=... not in allowlist` | 确认云端真实完整型号；不能只凭外壳或 App 显示名称扩展白名单 |
| `no matching product metadata` | 云端返回设备与产品未关联；需进一步检查关联字段，不能猜型号 |
| `read-only schema mismatch` | 按日志里的 DPS 定义适配；保留拒绝行为，不绕过校验 |
| `expected A01, got ...` | 设备协议不同，不能复用现有 A01 适配 |
| `finished ... a204=0` | 本次发现没有接受 a204；结合前面的跳过行、计数及账号排查 |
| `accepted model=roborock.wm.a204` | 已通过发现和订阅；若没有实体，再检查查询/平台加载错误 |
| `expected SDK 4.8.0, got ...` | SDK 不兼容，本次不会发现设备，不要强制降级共享依赖 |

先前仅在校验失败时保留异常类型，且未知型号直接跳过，所以旧日志不能给出上述原因。
本轮离线测试补充覆盖实际发现循环中的自有/共享 a204、a180 与 a204 并存、
型号跳过、缺失产品、A01/schema 拒绝和版本拒绝；不代表真实 a204 已验证。

日志设置参考：https://www.home-assistant.io/integrations/logger/
