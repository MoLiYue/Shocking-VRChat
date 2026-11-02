# PCS / LMS OSC 参数参考

PCS = Poiyomi Contact System，LMS = Lewd Motion System（名称取自本项目 `frontend/src/i18n/zh.ts`）。
两者都是 VRChat Avatar 的触碰交互组件包，底层都是 VRChat 的 **Contact Receiver**。

## 本文信息来源与可信度

写这份文档时没能拿到 PCS 官方参数手册（PCS 是付费/成人向 prefab，公开文档不可访问）。
下面按可信度分级标注，请区别对待：

| 标记 | 含义 |
|---|---|
| **[官方]** | VRChat 官方文档，权威 |
| **[实测]** | 在本仓库实际运行代码验证过 |
| **[项目]** | 本项目 README / 代码中确实存在的配置 |
| **[推断]** | 依据命名约定 + VRChat 机制推导，**未经官方文档或实机确认** |

标 **[推断]** 的含义仅供参考。要确认请用本文末尾的实测方法自行验证——这是电击设备，参数含义理解错会导致触发行为与预期不符。

## 一、底层机制：VRChat Contact Receiver **[官方]**

PCS 的每个 OSC 参数，本质是 avatar 上一个 Contact Receiver 组件的 `Parameter` 字段。
VRChat 把 animator 参数经 OSC 发出，地址固定为 `/avatar/parameters/<参数名>`。

Receiver Type 决定了参数的值语义，这是判断参数该用什么模式的关键：

| Receiver Type | 值行为 | 推荐数据类型 |
|---|---|---|
| **Proximity** | Float `0.0–1.0`，接触点越靠近接收器中心值越大。多个接触时取最大值 | Float |
| **Constant** | 有任何接触时置 1，无接触归 0 | Bool |
| **OnEnter** | 接触被检测到的那一帧置 1，**下一帧立即归 0** | Bool |

Proximity 的计算方式：从 sender 表面的最近点到 receiver 中心的距离。
box 形接收器可启用 `Use Face Proximity`，改为相对 +Z 面计算。

Advanced Parameters 还能额外生成一组参数（需在 avatar 侧显式开启，PCS 不一定用到）：

- `{参数名}_ProximitySpeed` [Float] — proximity 的**变化率**。仅 Proximity 类型生成
- `{参数名}_SenderVelocityMagnitude` [Float] — 接触者相对接收器的整体速度
- `{参数名}_PointSeparation` [Float] — 两者最近内点的世界空间距离（米）
- `{参数名}_SenderType` [Int] — 谁在碰：`0`=无/未识别，`1`=同一 avatar（自己），`2`=其他 avatar（别人），`3`=世界，`4`=生成物

> `_SenderType` 对本项目很有用：可以据此区分「自己摸」和「别人摸」。但需要 avatar 作者在 PCS 里开启 Advanced Parameters，默认大概率没有。**[推断]**

## 二、PCS 参数清单

来源：本项目与上游 `README_en.md` 的 Common Parameters 章节 **[项目]**。
原作者在该章节注明了 "Please help to supplement descriptions"，即含义本就缺失，故下表含义列多为 **[推断]**。

### Float 型（0.0–1.0，对应 Proximity）

| 参数 | 含义 | 可信度 |
|---|---|---|
| `pcs/contact/enterPass` | **最常用**。位于 PCS 触发入口，会**跟随被触发的位置自动切换** | [项目] 说明来自 README |
| `pcs/contact/proximityA` | 接近度 A 路。PCS 内部的多路接触通道之一 | [推断] |
| `pcs/contact/proximityB` | 接近度 B 路，与 A 对应 | [推断] |
| `pcs/contact/slide` | 滑动/摩擦位置量，随接触点沿轴向移动变化 | [推断] |
| `pcs/smash-intensity` | 碰撞强度，撞击力度越大值越高 | [推断] |
| `pcs/sps/pussy` | 指定部位触发 | [项目] |
| `pcs/sps/ass` | 指定部位触发 | [项目] |
| `pcs/sps/boobs` | 指定部位触发 | [项目] |
| `pcs/sps/mouth` | 指定部位触发 | [项目] |
| `pcs/sps/penis*` | 指定部位触发，带编号后缀，需用通配符 | [项目] |

`pcs/sps/` 与 `pcs/contact/enterPass` 的区别（README 原文确证）：
`enterPass` 会跟随 auto 模式的位置变化；**`pcs/sps/` 下的参数固定绑定部位，不跟随**。
所以要「只有特定部位被碰才触发」就用 `pcs/sps/*`。

### Bool 型（0/1，对应 Constant 或 OnEnter）

| 参数 | 含义 | 可信度 |
|---|---|---|
| `pcs/smash-intense` | 是否达到剧烈碰撞阈值 | [推断] |
| `pcs/contact/in` | 进入接触 | [推断] |
| `pcs/contact/out` | 离开接触 | [推断] |
| `pcs/contact/hit` | 命中/撞击瞬间，大概率是 OnEnter 型（仅 1 帧） | [推断] |

> **易混点**：float 的 `pcs/smash-intensity` 和 bool 的 `pcs/smash-intense` 是**两个不同参数**，词尾差一截。
> 本项目 `frontend/src/views/OverlimitRules.vue` 的超限规则示例用的是 `pcs/smash-intense == 1`。配置时注意别写错。**[项目]**

### LMS 参数

| 参数 | 类型 | 含义 | 可信度 |
|---|---|---|---|
| `lms-penis-proximityA*` | float | LMS **1.2** 的触发参数 | [项目] |
| `lms/contact/proximity` | float | LMS **1.3** 的触发参数（命名风格已改为斜杠分层） | [项目] |
| `lms-stroke-in` | bool | 进入冲程 | [推断] |
| `lms-stroke-out*` | bool | 离开冲程 | [推断] |
| `lms-stroke-smash` | bool | 冲程撞击 | [推断] |

LMS 1.2 与 1.3 命名规则不同，升级 avatar 后参数路径会变，需要重新配置。

## 三、本项目如何消费这些参数 **[实测/代码确证]**

### 类型处理

`srv/handler/base_handler.py` 的 `param_sanitizer()`：

| 输入类型 | 处理 |
|---|---|
| `float` | 钳制到 `[0.0, 1.0]`；NaN / ±Inf 一律**失效安全归 0** |
| `int` | 钳制到 `[0, 1]` |
| `bool` | `True`→1，`False`→0 |
| 其他 | 抛 `ValueError` |

所以 bool 型参数进来会变成 0/1 的离散值。配 distance 模式时它只有「满强度」和「零」两档，没有渐变——**bool 参数更适合 shock 模式**。

### 各模式对参数值的用法

| 模式 | 用法 | 适合的参数类型 |
|---|---|---|
| `distance` | 值越大越强，线性映射（可叠自定义曲线） | float（Proximity） |
| `shock` | 超过 `trigger_range.bottom` 即触发固定时长电击 | bool，或任意 float |
| `touch` | 取值的**变化率**（1阶速度/2阶加速度/3阶急动度） | float，且需持续变化 |
| `combo` | 短触发→shock，持续触摸→touch | float |
| `boost` | 超阈值则强度 +N，回零则 -N | bool |

> touch 模式的注意点 **[实测]**：它基于导数，**恒定不变的值导数为 0，不会有任何输出**。
> 实测恒定 0.6 输入 → 0 帧波形；递增输入 → 正常输出。被「握住不动」时 touch 模式静默是预期行为。

### 通配符匹配规则 **[实测]**

本项目把配置里的参数路径注册给 python-osc 的 Dispatcher（版本 1.10.2）。实测各类通配符在**配置端**的生效情况：

| 写法 | 是否生效 | 说明 |
|---|---|---|
| `pcs/sps/*` | **生效** | `*` 被转换为正则 `.*?`，**可跨 `/` 层级** |
| `pcs/*/enterPass` | **生效** | 中间段通配同样可跨层级 |
| `pcs/sps/?` | **不生效** | |
| `pcs/sps/{ass,mouth}` | **不生效** | |
| `pcs/sps/[ab]ss` | **不生效** | |

实测证据：注册 `pcs/sps/*` 能匹配到 `pcs/sps/pussy`，**也能匹配 `pcs/sps/deep/inner`**。

原因在 python-osc 1.10.2 `Dispatcher.handlers_for_address()` 的兼容分支：
当注册的地址含 `*` 时，它执行 `addr.replace("*", ".*?")` 再匹配传入地址，而 `.*?` 不受 `/` 限制。
标准 OSC 规范里 `*` 本应是 `[^/]*`（不跨层级），这条分支偏离了规范。

**实践含义**：`pcs/*` 这种写法会一次性吃掉 `pcs/` 下所有参数，范围比预期大得多，可能把 `smash-intensity`、`contact/hit` 等一起卷进同一个模式。建议写得具体些，例如 `pcs/sps/*` 而不是 `pcs/*`。

另外，前端输入框会自动补 `/avatar/parameters/` 前缀（`PARAM_PREFIX`，见 `frontend/src/views/ParamMap.vue`），填写时不用带。

## 四、自行实测验证参数（推荐）

上表的 **[推断]** 项，用本项目自带的录制器可以直接验证。这比查文档可靠，因为不同 PCS 版本、不同 avatar 的配置都可能不一样。

```bash
# 1. 录制。默认监听 9001，与本项目 osc.listen_port 相同
python osc_recorder.py -o pcs_probe

# 2. 进 VRChat，让人（或自己）依次触碰各个部位，动作尽量区分开：
#    轻触 → 停住不动 → 缓慢滑动 → 快速拍打 → 离开
# 3. Ctrl+C 停止，得到 pcs_probe.json
```

> **端口冲突**：录制器默认用 9001，和主程序是同一个端口，**两者不能同时运行**。
> 要边录边用，就按 README 的方案上 [osc-repeater](https://github.com/CyCoreSystems/osc-repeater) 把 VRChat 的 OSC 分发给两个程序，
> 或者给录制器换端口（`-p 9021`）并让 VRChat 同时发往该端口。

录制文件格式为 `{'t': 毫秒偏移, 'addr': 地址, 'args': [值]}`，可直接分析每个参数的：

- 实际值域（是否真的 0–1）
- 数据类型（float / bool）
- 触发时机与持续帧数（判断是 Constant 还是 OnEnter：**OnEnter 只有 1 帧**）
- 是否跟随触碰位置切换

快速统计脚本：

```python
import json, collections
d = json.load(open('pcs_probe.json'))
stat = collections.defaultdict(list)
for m in d['messages']:
    stat[m['addr']].append(m['args'][0])

for addr, vals in sorted(stat.items()):
    kind = type(vals[0]).__name__
    # bool 是 int 的子类，必须先排除，否则会被当数值统计
    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    rng = f"{min(nums):.3f}~{max(nums):.3f}" if nums else f"值集合={sorted(set(vals))}"
    print(f"{addr:<50} n={len(vals):<5} {kind:<6} {rng}")
```

输出示例：

```
/avatar/parameters/pcs/contact/enterPass    n=2   float  0.120~0.870
/avatar/parameters/pcs/contact/hit          n=1   bool   值集合=[True]
/avatar/parameters/pcs/smash-intensity      n=1   float  0.450~0.450
```

Web UI 的「OSC 录制」页面（`/recorder`）也能做同样的事，并且 Dashboard 可以实时看到 OSC 事件。

## 五、参考

- [VRChat 官方 Contacts 文档](https://creators.vrchat.com/avatars/avatar-dynamics/contacts/) — Receiver Type、Proximity 计算、Advanced Parameters 的权威定义
- [OSC 1.0 地址模式规范](https://opensoundcontrol.stanford.edu/spec-1_0.html#osc-address-patterns) — 通配符标准语义
- 本项目 `README.md` / `README_en.md` 的 Common Parameters 章节 — 参数清单原始出处

## 待补充

以下内容本次没能确认，欢迎补充：

- PCS 官方参数手册与完整参数列表（本文清单来自项目 README，可能不全）
- `proximityA` / `proximityB` 的确切分工
- `contact/slide` 的轴向定义与值域方向
- `smash-intensity` 的强度归一化方式
- `pcs/sps` 中 "sps" 的确切全称
- 各 bool 参数究竟是 Constant 还是 OnEnter 型
