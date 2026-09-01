# Unity LLM 告警面板演示与验收

## 实现链路

`visualization_server` 从实时 SUMO 状态提取 J16 四方向排队、等待、占有率、车速和信号相位，生成与微调数据一致的中文状态文本，并随 WebSocket 快照下发 Unity。Unity 点击“云脑分析当前路口”后调用 `POST http://127.0.0.1:8000/api/v1/llm/analyze`。

面板展示路口、事件、置信度、云脑延迟和中文管控建议。实时信号控制仍由 DQN 负责，LLM 不会未经校验直接修改信号相位。

## 录屏前启动

1. 启动 f32 GGUF 模型（不要换成 Q4/Q6）：

```powershell
cd tools\llama.cpp
.\llama-server.exe -m ..\..\models\llm\gguf\qwen-traffic-f32.gguf `
  --host 127.0.0.1 --port 8081 --n-gpu-layers 99 -c 2048 `
  --alias qwen-traffic --repeat-penalty 1.0
```

2. 在项目根目录分别启动：

```powershell
python server/api_server.py
python server/visualization_server.py --scenario real_peak
```

3. Unity 2022.3.62f2c1 打开 `frontend/CitySimulation`，进入 `Assets/Scenes/xiong_30.unity` 并点击 Play。

## 录屏操作

1. 等待左上角显示已连接，右下面板显示“J16（实时 SUMO 状态）”。
2. 让仿真运行 15–30 秒，展示车流和信号灯变化。
3. 点击“云脑分析当前路口”，正常等待约 5–7 秒。
4. 待“分析完成”后停留 8–10 秒，让观众读完事件和建议。
5. 旁白：“边缘侧 DQN 负责秒级实时控制，云端 LLM 基于实时路口状态进行慢周期事件研判，并生成可解释的管控建议。”

## 异常排查

- “尚未收到实时交通状态”：检查 8765 端口的 `visualization_server`。
- HTTP 503：检查 8081 端口的 `llama-server`和模型别名 `qwen-traffic`。
- HTTP 502/422：确认使用 f32 模型，查看 API 的 LLM 解析日志。
- HTTP 0 或超时：检查 8000 端口、防火墙和 `apiBaseUrl`。

## 验收标准

- Unity Console 无 C# 编译错误。
- J16 文本来自当前 SUMO 快照，不是固定样例。
- 请求期间按钮不可重复触发。
- 成功时展示 `event` / `confidence` / `latency_ms` / `advice`。
- API 或 LLM 未启动时显示可读错误，不卡死 Unity 主线程。
