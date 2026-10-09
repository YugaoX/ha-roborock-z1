# a204：HA 2026.9.2 测试与回滚（0.3.1）

用户云端日志已确认真实完整型号为 `roborock.cd.a204`，此前 `roborock.wm.a204` 是未确认的型号假设。
0.3.1 修正该精确白名单和统计，不扩展前缀匹配，不套用 a188 的状态名称或时间单位。
目前仅验证云端型号；a204 的 A01/schema 仍须下一轮实机日志确认。

本 Fork 的默认 `main` 与 `add-a204-support` 都包含精确型号 `roborock.cd.a204`。
设备自动发现，没有逐台添加 a204 的配置步骤。a204 的真实协议、状态码含义、
程序时间单位、控制效果及完成通知仍需实机验证。

## 为什么调整 SDK 版本

HA Core 2026.9.2 的内置 Roborock [manifest](https://github.com/home-assistant/core/blob/2026.9.2/homeassistant/components/roborock/manifest.json)
固定 `python-roborock==7.4.2`。上游 0.2.1 与本 Fork 早期 0.2.2 固定 4.8.0，
不适合直接在这一 HA 环境与内置集成共享依赖。

0.3.0 审查了官方 7.4.2 wheel 中的认证、v3 设备接口、设备解析、MQTT 和 A01 编解码。
现有使用的接口兼容；本轮把 manifest、运行时版本守卫、打包校验统一固定为 7.4.2。
运行时仍在线程中读取版本，并在发现请求前拒绝其他 SDK 版本；没有删除版本保护，
没有修改共享 SDK、类别枚举或官方集成。HACS 最低 HA 版本提高为 2026.9.2。
本轮没有安装完整 HA OS 或连接真实 a204；这是一份待用户实机验证的版本。

## 从头通过 HACS 安装

1. 备份 HA 配置，确认当前为 Core 2026.9.2。
2. HACS → 自定义存储库，添加 `https://github.com/YugaoX/ha-roborock-z1`，类型选 Integration / 集成。
   必须使用此 Fork 地址。现在直接安装默认分支 `main`，不用选择测试分支。
3. 搜索并下载“Roborock Z1 Max 洗衣机与干衣机”。此 Fork 暂无发布标签，HACS 可能显示 main 或提交号；
   核对最终 `<HA配置目录>/custom_components/roborock_z1_monitor/manifest.json`：
   `version` 为 `0.3.1`，`requirements` 为 `python-roborock==7.4.2`。
   旧 `0.2.1`/`0.2.2` 均不是本次版本。若仍下载旧版，刷新仓库信息并重新下载；
   也可从本 Fork main → Code → Download ZIP 手动放入组件目录。
4. 按下文开启本组件发现日志，再重启 HA。
5. 在 HA“设置 → 设备与服务”中保留或添加内置 Roborock 账号，完成登录。
   该账号应与能在 Roborock App 中看到在线 a204 的账号一致。
6. 添加“石头 Z1 Max”，选择这个 Roborock 账号。若原自定义集成条目还在，重启后核对原条目即可。
   内置 Roborock 即使不能初始化未知类别，也需要保留其已经成功建立的账号条目；不要删除授权。
7. 先查看只读实体，对照 App 的状态、程序时间与故障码。a204 完成提醒默认关闭，待自然结束信号验证后再手动启用，不接启动自动化。

若以后升级 HA，先核对新版本内置 Roborock 所需 SDK；本版本只审查了 7.4.2，不能强制安装它以降级共享依赖。

## 发现日志

在 `configuration.yaml` 现有 `logger.logs` 中加入组件项；没有 logger 时使用完整示例。
不要重复建立顶层 `logger:`，不要开启 SDK/HTTP 的全量调试。

```yaml
logger:
  default: warning
  logs:
    custom_components.roborock_z1_monitor: info
```

重启并添加集成后，在“设置 → 系统 → 日志”中显示原始日志，搜索 `Z1 discovery`。
将这些行和相关 `Z1 monitor setup failed` 错误发来，另提供 HA 当前版本。
不要上传账号、令牌、`.storage`、完整诊断包或家庭清单。
日志设置参考：[HA Logger](https://www.home-assistant.io/integrations/logger/)。

| 日志 | 判断 |
| --- | --- |
| `build=a204-cd-ha2026-9-1 sdk=7.4.2` | 本次诊断版已执行，SDK 版本符合要求 |
| 没有该 build 行 | 核对日志级别、安装路径、重启及是否添加本自定义集成 |
| `skipped model=... not in allowlist` | 云端实际完整型号不同；不能只凭 App 名称放宽白名单 |
| `no matching product metadata` | 云端设备与产品信息未关联，需要进一步查关联字段 |
| `read-only schema mismatch` | 按日志里的 DPS 定义继续适配，不绕过 schema 校验 |
| `expected A01, got ...` | 协议不同，现有 A01 路径不能直接使用 |
| `finished ... a204=0` | 没有接受 a204；结合前面的计数、跳过行与所选账号判断 |
| `accepted model=roborock.cd.a204` | 已通过发现和订阅；无实体时再检查查询与平台加载错误 |
| `expected SDK 7.4.2, got ...` | SDK 不兼容，在发现请求前拒绝；勿强制降级共享依赖 |

日志只主动记录型号、协议、计数、相关 schema 定义、SDK 版本与控制能力，
不记录账号、令牌、设备 ID、家庭 ID、设备名称或完整云端响应。

## 保留的校验与控制边界

- 精确白名单：a180/a188/a204；设备 `pv` 必须为 `A01`。
- `203/status`、`218/washing_left`、`220/error` 均必须为 `ro` + `VALUE`。
- `10000` 的 code 必须为 `id_query`；原实现没有校验该字段的 type/mode，本轮没有放宽或新增假设。
- 三个只读响应值必须为非负整数，不接受 bool，不用零代替缺失值。
- 启动须通过 `200/start` 的 `rw` + `BOOL`，以及 `204/mode`、`205/program`、`209/spin_level` 的 `rw` + `VALUE` 校验。
- 启动前重新查询，只有状态 1、故障 0、三个程序参数均为正整数才发送同包启动。
  60 秒防重复，超时不自动重试。7.4.2 的控制接口发送后不等待设备确认，成功返回不能证明已经启动。
- 控制字段不匹配时继续只读，启动按钮不可用；只读 schema 或协议不匹配时保持初始化失败，可能影响同一账号的其他设备。
- a204 显示原始状态码、时间原始值；schema 相同不能证明数值含义相同。
  完成检测规则仍来自 a180/a188，所以 a204 完成提醒默认关闭，且属性注明尚未实测；a180/a188 原有默认设置保持不变。
- 只有确认 a204 数值语义且现场有人观察时，才人工测试一次启动，不把按钮接入自动化。

## 离线验证与回滚

```sh
python -m pip install python-roborock==7.4.2
python -m unittest discover -s tests -v
python scripts/build_release.py
```

29 项离线测试通过，包含真实 SDK 导入/账号解析/发现与 A01 查询、启动报文编解码，
以及自有/共享 a204、a180/a204 并存、schema/协议/版本拒绝、重复启动保护和通知规则。
网络、云端和 MQTT 使用模拟对象；不向真实设备发送命令，也未验证完整 HA 运行环境。
CI 同样先安装 7.4.2 再运行测试。

安装失败时恢复备份的组件目录或移除本自定义集成，再重启；保留内置 Roborock 账号。
在 HA 2026.9.2 上回滚自定义集成时，不要回滚到要求 SDK 4.8.0 的旧安装包。
代码修改保留在独立分支与提交历史中，可按需要撤销提交。
