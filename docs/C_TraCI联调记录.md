# C 同学 TraCI 联调记录

## 使用的路网交付物

| 项目 | 位置 |
|---|---|
| SUMO 配置 | `sumo_files/xiongan_30.sumocfg` |
| 路网 | `sumo_files/xiongan_30.net.xml` |
| 进口车道映射 | `docs/lane_mapping.json` |
| TLS 动作映射 | `docs/tls_mapping.json` |

## 后端配置

`server/api_server.py` 默认使用上述配置；如需切换场景或机器上的路径，启动前设置：

```powershell
$env:XIONGAN_SUMO_CONFIG = '绝对路径\\xiongan.sumocfg'
```

服务启动前会预校验 SUMO 文件、30 个 `J01`–`J30` 信号灯和每个路口恰好 4 个相位。

## 联调验收闭环

1. `POST /api/v1/simulation/start` 建立 TraCI 会话；
2. `GET /api/v1/simulation/state` 返回 660 维 `float32` 语义状态；
3. `POST /api/v1/simulation/actions` 接收完整的 30 路口动作并推进仿真；
4. `GET /api/v1/simulation/rewards` 返回 `J01`–`J30` 的 V5.1 奖励和全局平均奖励；
5. `POST /api/v1/simulation/stop` 关闭 TraCI 会话。

正式回归命令：

```powershell
& D:\ChallengeCup2026\.venv-xiongan-c\python.exe -m pytest -q
```

## 正式模型接入后的契约

- 状态顺序：`J01 → J30`，每路口连续 22 维，总共 660 维；
- 推理服务为每个路口追加 4 维需求门控掩码，正式模型实际输入 26 维，输出动作 `0`–`3`；
- `/api/v1/model/predict` 已接入版本化正式模型，并返回按路口 ID 组织的 30 个动作；
- 调用方将预测响应中的 `actions` 原样提交至 `/api/v1/simulation/actions`；
- 任何状态维度、动作含义或奖励版本变更，须先更新 `docs/接口文档.md`。
