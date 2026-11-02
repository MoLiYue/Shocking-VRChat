# Neko-VRC 的 SPS2 / OGB 实现方式

调研对象：<https://github.com/NekoCitrus/Neko-VRC>（`main` 分支）

该项目与本项目同源（同样的 `srv/handler`、`srv/connector`、`doc/dglab` 结构，主文件也叫 `shocking_vrchat.py`），
但围绕 SPS/OGB 深度读取做了大量重构。它的 README 第一句就是「通过 VRChat OSC 读取 Avatar SPS/OGB 插入深度」，
即把 SPS 深度作为**主要触发源**，而本项目原本以 PCS/LMS 的单值 proximity 为主。

本文记录它的做法，以及本项目据此实现 SPS2 兼容时采纳/未采纳的部分。

## 一、最重要的结论：OGB 参数确实会经 OSC 发出

这解答了 `doc/sps2_vs_sps1_osc.md` 2.3 节留下的未决点。

Neko-VRC 的 `srv/sps_depth.py` 直接**解析 VRChat 生成的 avatar OSC 配置 JSON**：

```
%USERPROFILE%\AppData\LocalLow\VRChat\VRChat\OSC\<userId>\Avatars\<avatarId>.json
```

它遍历该 JSON 的 `parameters[]`，取 `output.address` 和 `name` 两个字段，
筛选 `name` 以 `OGB/Orf/` 或 `OGB/Pen/` 开头的项（`_zone_from_parameter()`）。

**这说明 OGB 的 depth 参数出现在 VRChat 的 OSC config 里，因此会通过 OSC 发出。**
一个有可运行单元测试的项目依赖这条路径工作，这是比源码推断更强的证据。

我之前从 VRCFury 源码看到 depth 参数是 `synced = false` 而产生的疑虑，结论是：
**`synced` 只影响网络同步，不决定 OSC 可见性**。本地 OSC 输出覆盖范围比 synced 参数更宽。

## 二、OGB 参数命名与信号集

地址结构（`sps_depth.py` 的 `sps_osc_bindings()`）：

```
/avatar/parameters/OGB/Orf/<zone_id>/<signal>     ← Socket（Orifice）
/avatar/parameters/OGB/Pen/<zone_id>/<signal>     ← Plug（Penetrator）
```

`zone_id` 是部位标识，取自地址第 6 段，因 avatar 而异（对应 VRCFury 里可自定义的 `oscId`）。

该项目实际订阅的 signal：

| 触发类型 | signal | 用途 |
|---|---|---|
| Socket | `PenSelfNewRoot` / `PenSelfNewTip` | **SPS2 新机制**，自己的 plug 的根部/尖端 proximity |
| Socket | `PenOthersNewRoot` / `PenOthersNewTip` | 同上，别人的 plug |
| Socket | `PenSelf` / `PenOthers` | **旧机制（SPS1/legacy）**，单值深度 |
| Socket | `PenOthersClose` | 门控信号，详见下文 |
| Plug | `PenSelf` / `PenOthers` | plug 侧深度，直接可用 |

测试文件里还出现了 `TouchSelf`、`FrotSelf`，但 `has_socket_depth_parameters()` 的注释明确写了
**Touch/Frot 信号不能当作插入深度使用**，只有直接 depth 或配对的 Root/Tip 才算。

### SPS1 与 SPS2 在 OSC 层面的真正区别

这是本次调研最有价值的一点：

| | 参数形态 | 消费方式 |
|---|---|---|
| **SPS1 / legacy** | `PenSelf` / `PenOthers` 单个 0–1 值 | 直接当深度用 |
| **SPS2** | `PenSelfNewRoot` + `PenSelfNewTip` **一对** | **必须自己算**，两个 proximity 推出插入深度 |

所以 SPS2 对 OSC 消费端的影响不是「参数消失」，而是**语义从单值变成了需要推算的一对值**。
只读 `PenSelf` 的老工具在纯 SPS2 avatar 上会拿到 0 或拿不到参数。

## 三、深度推算算法

### 3.1 Plug 侧（简单）

```
depth = max(PenSelf, PenOthers)
```

### 3.2 Socket 侧（SPS2 Root/Tip 推算）

核心难点：Root/Tip 是两个 proximity 值（0–1，越近中心越大），要从中还原「插进去多少」。
需要先知道 plug 的**长度**，而长度未知且因人而异，所以要动态估算。

`_PenetratorLengthDetector`（注释标明是 OGB 算法的移植）：

```python
length = tip_proximity - root_proximity      # 瞬时长度估计
```

采样过滤规则：

| 条件 | 处理 | 原因 |
|---|---|---|
| root < 0.01 或 tip < 0.01 | 清空全部状态 | 已脱离，样本无效 |
| root > 0.95 | 忽略本次 | 根部已到中心，长度不可信 |
| length < 0.02 | 忽略本次 | 太小，噪声 |
| tip > 0.99 | 记为 `penetrating_sample`，只保留最大值 | 完全插入状态下的长度 |
| 其他 | 存入 `recent_samples`（最多 8 个） | 正常采样 |

`_recalculate()` 取长度值的方式不是平均也不是中位数，而是：
排序后找**相邻差值最小的那一对**，取其中较大者。即「找最密集聚集处」，对离群值比平均数稳健。
样本不足 4 个时退回用 `penetrating_sample`。

最终深度（`_new_socket_depth`）：

```python
if length and tip > 0.99:                 # 仅在完全插入时给非零深度
    exposed_ratio = (1 - root) / length   # 露在外面的比例
    depth = clamp(1 - exposed_ratio)
else:
    depth = 0.0
```

### 3.3 新旧机制的回退与 `PenOthersClose` 门控

`_socket_depth(owner)` 的优先级：

1. 先试 SPS2 的 Root/Tip 推算（`_new_socket_depth`）
2. 若 Root/Tip 不可用（缺失或都 ≤ 0），回退到旧的 `PenSelf` / `PenOthers` 单值
3. 回退路径上，若存在 `PenOthersClose` 且其值为 0，则深度强制为 0

第 3 条是个兼容性细节：`PenOthersClose` 是接近门控，OGB 用它避免远处的误触发。
该项目的测试 `test_legacy_close_gate_matches_ogb_without_overriding_new_depth` 明确验证了
**门控只作用于旧路径，不能覆盖新 Root/Tip 算出的深度**。

最终 `depth` 属性对 Self / Others **取最大值**，不区分是谁触发：

```python
depth = max(_socket_depth('Self'), _socket_depth('Others'))
```

README 说明了这个设计：自身 Socket 与自身 Plug 交互同样参与计算，
需要在 VRChat 开启 `Avatar Self Interact`。

## 四、OGB_ENABLED 心跳

Neko-VRC 每 5 秒向 VRChat **发送**一个布尔参数：

```
/avatar/parameters/OGB_ENABLED = true        (OGB_ENABLED_INTERVAL = 5.0)
```

作用是告知 avatar「有 OGB 兼容工具在监听」，avatar 侧据此决定是否输出深度参数。

实现要点（`srv/oscquery.py` 的 `send_ogb_enabled()`）：

- **目标端口不能假定**。代码注释特别强调「OSCQuery HTTP 端口不是 VRChat 的 OSC 接收端口」，
  每次心跳都重新请求 `<endpoint>/?HOST_INFO`，从中读 `OSC_PORT` / `OSC_IP` / `OSC_TRANSPORT`
- 校验 `OSC_TRANSPORT == 'UDP'`、端口在 1–65535、`HOST_INFO` 响应不超过 64 KiB
- `OSC_IP` 是未指定地址（0.0.0.0）时回退用 endpoint 的 hostname
- 发完立即 `client._sock.close()`，不留常驻 socket
- **退出时不发 `false`**，注释说明原因：可能还有其他 OGB 兼容程序在运行，发 false 会干扰它们
- 与 Chatbox、设备配对、输出暂停开关都**互相独立**

> 可信度说明：`OGB_ENABLED` 在 OGB 官方文档仓库（OscToys/osc.toys）里**没有找到记载**，
> 我检索了它全部 4 个文档文件，无命中。本节内容来自 Neko-VRC 的实现与其单元测试
> `tests/test_ogb_heartbeat.py`（该测试断言了地址、5 秒间隔、失败重试行为）。
> 即它是经过实现验证的做法，但我没能找到上游官方规格来交叉确认。

## 五、参数发现：OSCQuery

Neko-VRC 不要求用户手填参数路径，而是自动发现：

- 通过 zeroconf 发现 `_oscjson._tcp.local.` 和 `_osc._udp.local.` 服务
- HTTP 轮询 OSCQuery 端点拿参数树（`poll_interval=0.25`，`request_timeout=1.5`）
- 解析出当前 avatar 的 SPS 部位列表，供 UI 下拉选择
- 另有 `_endpoint_from_game_log()`，从 VRChat 游戏日志兜底推断端点
- `/avatar/change` **仅用于要求立即刷新**，不作为数据来源

它还有一套 HTTP 读数的时序防护（`receive_query_value`）：
用 `time.perf_counter()` 而非 monotonic（注释说 Python 3.10 的 Windows monotonic 时钟精度不足，
无法正确排序「快速热保存」与「在途 HTTP 请求」），并且 UDP 实时值优先于 HTTP 轮询值。

## 六、本项目采纳了什么、没采纳什么

| Neko-VRC 的做法 | 本项目 | 理由 |
|---|---|---|
| `SPSDepthCalculator` 深度推算 | **已移植** | 这是 SPS2 兼容的核心，不可替代 |
| `_PenetratorLengthDetector` 长度估算 | **已移植** | 同上 |
| Root/Tip → 深度，含 legacy 回退与 Close 门控 | **已移植** | 同上 |
| `OGB_ENABLED` 心跳 | **已实现（简化）** | 本项目直接发往配置的 OSC 端口，不走 OSCQuery HOST_INFO 探测 |
| OSCQuery + zeroconf 自动发现部位 | **未采纳** | 本项目的交互模型是用户在「参数管理」里手填路径，配合可跨层级的 `*` 通配即可覆盖一个 zone 的全部 signal。引入 zeroconf 会增加依赖和复杂度 |
| avatar OSC JSON 解析 | **未采纳** | 同上，且该路径是 Windows 专属，不利于 Linux 下开发调试 |
| HTTP 轮询 + 时序防护 | **未采纳** | 没有 HTTP 读数来源，不需要 |

架构差异也是未全量移植的原因：Neko-VRC 把 `osc_handler` 签名改成了
`osc_handler(self, address, binding, *args)`，即每个地址都携带一个 `(trigger_type, signal)` 绑定；
本项目保持 `osc_handler(self, address, *args)`，改签名会牵动全部现有模式。
本项目改为在 handler 内部按地址自行解析 signal，侵入面更小。

## 七、参考

- <https://github.com/NekoCitrus/Neko-VRC> — `srv/sps_depth.py`、`srv/oscquery.py`、`tests/test_ogb_heartbeat.py`、`tests/test_live_settings.py`
- <https://vrcfury.com/sps> — SPS2 官方文档
- <https://github.com/OscToys/osc.toys> — OGB 官方文档仓库（未包含 OGB_ENABLED 与参数命名细节）
- 本仓库 `doc/sps2_vs_sps1_osc.md` — SPS1/SPS2 区别与 OSC 影响
- 本仓库 `doc/pcs_osc_params.md` — PCS/LMS 参数与 Contact Receiver 机制
