# 路网接口说明

## 固定路口顺序

`J01, J02, ..., J20`

后端接收 `actions[20]` 时，`actions[0]` 对应 J01，`actions[19]` 对应 J20。

## 状态接口

每个路口 22 维，全局状态固定为 `20 × 22 = 440` 维。进口方向必须从 `docs/lane_mapping.json` 读取，禁止再靠 E0/E1 这类无方向含义的编号猜测。

## TLS 接口

每个路口恰好 4 个 phase，动作索引与 phase 索引一一对应。TraCI 可直接：

```python
traci.trafficlight.setPhase(junction_id, action)
```

生产环境建议在动作切换时由控制器额外插入黄灯过渡；黄灯不是强化学习动作。
