# SPS 1 与 SPS 2 的区别，以及对 OSC 的影响

SPS = **Super Plug Shader**，VRCFury 的 VRChat 触觉（haptics）变形系统。
它是 DPS（Raliv Dynamic Penetration System）和 TPS（Poiyomi Penetrator）的后继者。

## 先说一个必须澄清的混淆点

**本项目配置里的 `pcs/sps/*` 参数，和这里讲的 VRCFury SPS 不是同一个东西。**

证据：VRCFury 源码中，SPS 生成的 contact 参数命名空间是 `OGB/Orf/...`（socket）和 `OGB/Pen/...`（plug），
**不存在 `pcs/sps/` 这种路径**（`BakeHapticSocketsService.cs:180`、`BakeHapticPlugsService.cs:178`）。

所以 `/avatar/parameters/pcs/sps/pussy` 属于 PCS 自己的命名空间，只是缩写撞了。
配置本项目时不要把两者的文档混用。（这一条同时回答了 `doc/pcs_osc_params.md` 里「sps 全称待确认」那一项的一半——至少确认了它不是 VRCFury 的 SPS。）

## 一、SPS1 vs SPS2 核心区别 **[官方]**

来源：<https://vrcfury.com/sps>、<https://vrcfury.com/sps/upgrade>

SPS2 已是 VRCFury 最新稳定版的默认实现，官方定位是「DPS、TPS、SPS1 的统一替代品」。

| 维度 | SPS1 | SPS2 |
|---|---|---|
| **变形驱动机制** | 依赖 lights + contacts | **SPS2↔SPS2 之间既不需要 lights 也不需要 contacts** |
| **数量限制** | 存在 light-conflict 问题，socket 基本一次只能开一个 | 支持远多于 SPS1 的 socket/plug，可多个同时启用 |
| **定向过滤** | 基本没有 | 完整 tag/channel 系统：socket 最多 2 个自定义 tag，plug 最多 2 个 include + 2 个 exclude，且每条可区分 Self / Others |
| **自动部位 tag** | 无 | 按骨骼自动打 tag：`hips`、`head`、`chest`、`hand`/`handleft`/`handright`、`foot`/`footleft`/`footright`；髋部放两个时自动分 `hipsfront`/`hipsback` |
| **引导路径** | 无 | socket 可定义最多 3 个 path stop，plug 进入后沿路径被引导，路段可选择性收缩 |
| **表面贴合** | — | Radius Offset，按 plug 半径偏移目标点（手部 socket 尤其有用） |
| **mesh 支持** | 需要 rigged | rigged 与 un-rigged 都支持 |
| **blendshape** | 变形时受限 | 支持变形期间继续播放指定 blendshape |
| **缩放** | 有问题 | 正确支持 avatar scaling 与 mesh scaling |
| **包围盒** | plug 会增大 avatar bounding box | 不再增大 |
| **开销模型** | 每个 plug/socket 都带 lights | 每个 plug/socket 多占 **2 个 material slot**；grab pass 全世界共用 **2 个**（不是每个物件 2 个） |
| **向后兼容** | — | 开启 Legacy Compatibility 后可与 SPS1 / DPS / TPS 互通，**但该路径仍然使用 lights** |

升级方式（官方）：已用 VRCFury SPS 的话，更新 VRCFury 再重新上传即可自动变成 SPS2；
DPS/TPS 则走 `Tools > VRCFury > SPS > Upgrade DPS to SPS`。

## 二、对 OSC 的影响

这是本文重点。要讲清楚需要三段推理，前两段有确证，第三段有一个未决点。

### 2.1 OSC 参数的来源是 Contact Receiver **[官方]**

VRChat 的 `/avatar/parameters/<名字>` 来自 avatar 的 animator 参数，而触碰类参数由
**Contact Receiver** 组件写入（详见 `doc/pcs_osc_params.md` 第一节）。
**没有 contact，就没有触碰类 OSC 参数。**

### 2.2 SPS2 砍掉了变形用的 contacts，但保留了 depth/haptics 用的 contacts **[官方]**

官方文档三处明确说明（原文）：

> - SPS2 deformation does not use lights or contacts between SPS2 users.
> - Legacy compatibility still uses lights so SPS2 can interact with SPS1, DPS, and TPS.
> - **Depth animations and some haptics features still use contacts even though deformation itself no longer does.**

所以这是个**部分**移除，而非全部移除：

| 用途 | SPS1 | SPS2 |
|---|---|---|
| 变形本身 | lights + contacts | 不用（SPS2↔SPS2） |
| 与 SPS1/DPS/TPS 互通 | — | 仍用 lights（需开 Legacy） |
| **Depth animations / 部分 haptics** | contacts | **仍用 contacts** |

**结论：触觉联动类工具依赖的是 depth/haptics 那条 contact 管道，这条 SPS2 保留了。**
纯粹只服务于变形的 contact 才消失。

官方同时列出了 depth animation **不工作**的情形，这些就是 OSC 侧会「没数据」的场景：

- 目标是 world socket / object，没有 avatar contact 管道
- 对方 avatar 仍是**未升级的 DPS**（官方建议让对方装 VRCFury 跑一次 Upgrade）

另外一个容易忽略的坑：socket 上关掉 Legacy Compatibility 后，它变成 SPS2-only、不再生成 legacy lights，
于是**和仍在用 SPS1/DPS/TPS 的人互动会失效**。对以「被别人触碰」为触发条件的工具，这等于触发源直接消失。

### 2.3 SPS 的 depth 参数叫什么，以及它是否真的出现在 OSC 里 **[源码] + 一个未决点**

从 VRCFury 源码（`main` 分支）读到的实际命名：

| 位置 | 参数前缀 | 出处 |
|---|---|---|
| Socket | `OGB/Orf/<oscId>` | `BakeHapticSocketsService.cs:180` |
| Plug | `OGB/Pen/<name>` | `BakeHapticPlugsService.cs:178` |

> `oscId` 是 socket/plug 上可由作者自定义的字段（`VRCFuryHapticSocket.cs:31`），
> 所以前缀中间那段**因 avatar 而异**，不是固定值。
> OGB 来自作者的配套工具 OscGoesBrrr。

该前缀下的子参数（`SpsDepthContacts.cs`）：

```
OGB/Orf/<id>/Contact            OGB/Orf/<id>/Dist/Meters
OGB/Orf/<id>/Contact/Tip        OGB/Orf/<id>/Dist/PlugLens/Vel
OGB/Orf/<id>/Contact/Root       OGB/Orf/<id>/Dist/Local/Vel
OGB/Orf/<id>/Contact/Width      OGB/Orf/<id>/Length/Inverted
```

**已解决（2026-11-02 更新）**：这些 depth 参数在源码里是**非 synced** 的，但这**不影响 OSC 可见性**。

`HapticContactsService.AddReceiver()` 用 `fx.NewFloat(req.paramName, usePrefix: req.usePrefix)` 创建参数，
而 `ControllerManager.NewFloat()` 的签名是 `NewFloat(string name, bool synced = false, ...)`——synced 默认 false，这里没有覆盖它。

我原本据此怀疑 depth 数据拿不到。但调研 Neko-VRC（`doc/neko_vrc_sps2_research.md`）后确认：
该项目直接解析 VRChat 生成的 avatar OSC 配置 JSON，从中筛选 `OGB/Orf/`、`OGB/Pen/` 开头的参数，
**说明 OGB depth 参数确实出现在 OSC config 里，会通过 OSC 发出**。
一个带可运行单元测试、以此为核心功能的项目印证了这条路径。

结论：**`synced` 只影响网络同步，不决定本地 OSC 输出范围。** VRChat 文档说的
「sending every possible message」范围比 synced 参数更宽。本仓库已据此实现 SPS2 兼容
（`srv/sps_depth.py`），并实测验证了深度聚合可用。

作为对比，源码里显式标 `synced: true` 的是开关类参数：

| 参数 | 说明 | 出处 |
|---|---|---|
| `<oscId>` | socket 的开关，参数名就是 oscId | `BakeHapticSocketsService.cs:146` |
| `autoMode` | Auto Mode 开关 | 同上 `:82` |
| `stealth` | Stealth Mode 开关 | 同上 `:99` |
| `tipLight` | plug tip light 开关 | `BakeHapticPlugsService.cs:126` |
| `VFH/Version/<ver>` | haptics 版本标记 | `BakeHapticVersionsService.cs:29` |

还有一点本文初稿未覆盖、后来才确认的：**SPS2 的 socket depth 不是单值，而是 `PenSelfNewRoot` +
`PenSelfNewTip` 一对 proximity，必须自行推算插入深度**（SPS1 的 `PenSelf` 是单值可直接用）。
算法见 `doc/neko_vrc_sps2_research.md` 第三节。这是 SPS1→SPS2 对 OSC 消费端最实质的影响。

顺带一提，`FullController` 里有 `injectSpsDepthParam` / `injectSpsVelocityParam` 两个字段，
可以把「最近的 SPS depth / velocity」注入到你自己指定的参数名上。
它们在源码里已标注 **(Deprecated)，建议改用 Inject Parameters**（`FullControllerBuilder.cs:788-789`）。
如果 OGB 原始参数确实不过 OSC，这类注入机制就是把 depth 暴露成自定义（可 synced）参数的正途。

## 三、实测确认方法

用本项目自带的录制器，5 分钟就能把 2.3 的未决点敲定：

```bash
# 若主程序正在占用 9001，换个端口并让 VRChat 同时发往该端口
python osc_recorder.py -p 9001 -o sps2_probe
```

进 VRChat，穿上用 SPS2 的 avatar，开启 socket，做一次接触动作，然后看录制结果：

```bash
python3 -c "
import json, collections, re
d = json.load(open('sps2_probe.json'))
stat = collections.defaultdict(list)
for m in d['messages']:
    stat[m['addr']].append(m['args'][0])
# 覆盖下方判读表的全部信号：depth 参数 + 开关类参数
pat = re.compile(r'OGB/|SPS|VFH/|autoMode|stealth|tipLight', re.I)
for a, v in sorted(stat.items()):
    if pat.search(a):
        print(f'{a:<60} n={len(v):<4} {v[:3]}')
"
```

判读：

| 观察到 | 结论 |
|---|---|
| 出现 `OGB/Orf/.../Contact` 之类并且数值连续变化 | OSC 输出非 synced 参数，depth 可直接用于强度映射 |
| 只出现 socket 开关名 / `autoMode` / `stealth` / `VFH/Version/*` | depth 不过 OSC，需要走 Inject Parameters 自建 synced 参数 |
| 什么都没有 | 先 Action Menu > Options > OSC > Reset Config，再确认 avatar 真的烘焙了 SPS 组件 |

换过 avatar 或改过参数后一定要 Reset Config，否则 VRChat 会继续用旧的缓存配置
（配置缓存在 `AppData\LocalLow\VRChat\VRChat\OSC\<userId>\Avatars\<avatarId>.json`）。

## 四、对本项目使用者的实际建议

1. **升级 SPS2 本身不会让现有 OSC 触发失效**——depth/haptics 的 contact 管道官方明确保留了。
2. **但别关 socket 的 Legacy Compatibility**，除非确认圈子里没人还在用 SPS1/DPS/TPS。关掉后这些人碰你不会产生任何 contact，触发直接消失。
3. 如果对方用的是**未升级的 DPS**，depth animation 不工作，建议让对方跑一次 VRCFury 的升级。
4. 真正稳妥的触发源仍然是 avatar 作者**显式暴露给 OSC 的参数**（PCS 的 `pcs/contact/*`、`pcs/sps/*`，LMS 的 `lms-*` 等）。
   这些是作者主动放进 Expression Parameters 的，不受 SPS 内部实现变化影响。
   把设备触发绑在 SPS 的内部参数上本身就比较脆弱。
5. SPS2 的 tag 系统里，plug 的 include/exclude 可以区分 **Self / Others**。
   如果想实现「只有别人碰才电」，这比在 OSC 侧猜更可靠——不过它作用在 avatar 构建期，需要改 avatar 而非改本程序配置。

## 五、参考

- [VRCFury SPS 官方文档](https://vrcfury.com/sps) — SPS2 benefits、Important Notes、legacy compatibility、tags
- [VRCFury 升级到 SPS2](https://vrcfury.com/sps/upgrade)
- [VRChat Contacts 官方文档](https://creators.vrchat.com/avatars/avatar-dynamics/contacts/) — Receiver Type 与参数生成
- [VRChat OSC 参数文档](https://docs.vrchat.com/docs/osc-avatar-parameters) — config 自动生成与缓存位置
- VRCFury 源码 `main` 分支 — 参数命名与 synced 标记，文中已逐条标注文件行号
- 本仓库 `doc/pcs_osc_params.md` — PCS/LMS 参数与 Contact Receiver 基础机制

## 待确认

- `OGB/Orf/<id>/Contact/Tip|Root|Width` 各自的确切几何含义与值域
- `Dist/PlugLens/Vel` 与 `Dist/Local/Vel` 的区别
- `OGB_ENABLED` 的官方规格（OGB 文档仓库 OscToys/osc.toys 中未找到记载，
  目前实现依据是 Neko-VRC 的代码与其单元测试）
- PCS 的 `pcs/sps/` 中 sps 的全称（已确认**不是** VRCFury SPS——VRCFury 的命名空间是 `OGB/`，
  但其本义仍未知）

## 已解决

- ~~OSC 是否输出非 synced 的 animator 参数~~ → **会输出**，详见 2.3 节
- ~~OscGoesBrrr 的官方文档地址~~ → <https://github.com/OscToys/osc.toys>
  （但该仓库不含参数命名与 OGB_ENABLED 细节）
