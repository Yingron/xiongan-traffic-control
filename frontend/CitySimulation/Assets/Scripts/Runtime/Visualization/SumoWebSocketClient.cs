using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace CitySimulation.Runtime.Visualization
{
    /// <summary>云端 LLM 诊断结果（对应后端 type=llm_alert 消息）。</summary>
    [Serializable]
    public class LlmAlertData
    {
        public string type;
        public string junction;
        public string event_cn;      // JSON key "event"（C# 保留字，解析时改名）
        public string event_en;
        public float confidence;
        public string advice;
        public float latency_ms;
        public float sim_time;
        public string sim_clock;
        public string scenario;
        public string llm_backend;

        /// <summary>JsonUtility 解析；"event" 是 C# 保留字，先把 key 改名为 event_cn。</summary>
        public static LlmAlertData FromJson(string raw)
        {
            var renamed = System.Text.RegularExpressions.Regex.Replace(
                raw, "\"event\"\\s*:", "\"event_cn\":");
            return JsonUtility.FromJson<LlmAlertData>(renamed);
        }
    }

    /// <summary>
    /// WebSocket 客户端 — 连接 Python 可视化服务器，接收 SUMO 仿真状态。
    /// 使用 .NET 内置 ClientWebSocket，无需第三方库。
    /// 在后台线程接收数据，通过队列传递到主线程。
    /// </summary>
    [DisallowMultipleComponent]
    public class SumoWebSocketClient : MonoBehaviour
    {
        [Header("连接配置")]
        [Tooltip("Python 可视化服务器地址")]
        public string serverHost = "127.0.0.1";
        [Tooltip("WebSocket 端口")]
        public int serverPort = 8765;
        [Tooltip("是否在 Start 时自动连接")]
        public bool autoConnect = true;
        [Tooltip("断线重连间隔（秒）")]
        public float reconnectInterval = 3f;

        // ── 公开状态 ──
        public bool IsConnected => _ws != null && _ws.State == WebSocketState.Open;
        public string CurrentScenario { get; private set; } = "";
        public string ScenarioLabel { get; private set; } = "";

        // ── 事件 ──
        /// <summary>收到完整状态消息（已解析为 JSON 字符串）</summary>
        public event Action<string> OnStateMessage;
        /// <summary>连接状态变化</summary>
        public event Action<bool> OnConnectionChanged;
        /// <summary>收到场景切换确认</summary>
        public event Action<string, string> OnScenarioSwitched;
        /// <summary>收到云端 LLM 诊断结果（type=llm_alert）</summary>
        public event Action<LlmAlertData> OnLlmAlertReceived;
        /// <summary>云脑诊断失败（type=llm_alert_error，如 llama-server 未启动）</summary>
        public event Action<string> OnLlmAlertError;

        // ── 内部状态 ──
        ClientWebSocket _ws;
        CancellationTokenSource _cts;
        readonly ConcurrentQueue<string> _messageQueue = new();
        float _reconnectTimer;
        bool _wasConnected;

        void Start()
        {
            if (autoConnect)
            {
                _ = ConnectAsync();
            }
        }

        void Update()
        {
            // 处理主线程消息
            while (_messageQueue.TryDequeue(out var msg))
            {
                HandleMessage(msg);
            }

            // 断线重连
            if (!IsConnected)
            {
                if (_wasConnected)
                {
                    _wasConnected = false;
                    OnConnectionChanged?.Invoke(false);
                }
                _reconnectTimer += Time.deltaTime;
                if (_reconnectTimer >= reconnectInterval && autoConnect)
                {
                    _reconnectTimer = 0f;
                    _ = ConnectAsync();
                }
            }
            else if (!_wasConnected)
            {
                _wasConnected = true;
                OnConnectionChanged?.Invoke(true);
            }
        }

        async Task ConnectAsync()
        {
            if (IsConnected) return;

            _cts?.Cancel();
            _cts = new CancellationTokenSource();

            try
            {
                _ws?.Dispose();
                _ws = new ClientWebSocket();
                var uri = new Uri($"ws://{serverHost}:{serverPort}");
                await _ws.ConnectAsync(uri, _cts.Token);
                Debug.Log($"[SumoWS] 已连接 → {uri}");

                _ = ReceiveLoopAsync(_cts.Token);
            }
            catch (Exception e)
            {
                if (!_cts.IsCancellationRequested)
                {
                    Debug.LogWarning($"[SumoWS] 连接失败: {e.Message}");
                }
            }
        }

        async Task ReceiveLoopAsync(CancellationToken ct)
        {
            var buffer = new byte[65536];
            var sb = new StringBuilder();

            try
            {
                while (!ct.IsCancellationRequested && _ws.State == WebSocketState.Open)
                {
                    var result = await _ws.ReceiveAsync(buffer, ct);

                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        break;
                    }

                    sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));

                    if (result.EndOfMessage)
                    {
                        _messageQueue.Enqueue(sb.ToString());
                        sb.Clear();
                    }
                }
            }
            catch (OperationCanceledException) { }
            catch (Exception e)
            {
                if (!ct.IsCancellationRequested)
                {
                    Debug.LogWarning($"[SumoWS] 接收异常: {e.Message}");
                }
            }
        }

        void HandleMessage(string raw)
        {
            try
            {
                var msg = JsonUtility.FromJson<WsMessage>(raw);
                if (msg == null) return;

                switch (msg.type)
                {
                    case "connected":
                        CurrentScenario = msg.scenario ?? "";
                        ScenarioLabel = msg.scenario_label ?? "";
                        Debug.Log($"[SumoWS] 服务器确认 — 场景: {ScenarioLabel}");
                        break;

                    case "state":
                        OnStateMessage?.Invoke(raw);
                        break;

                    case "scenario_switched":
                        CurrentScenario = msg.scenario ?? "";
                        ScenarioLabel = msg.scenario_label ?? "";
                        OnScenarioSwitched?.Invoke(msg.scenario ?? "", msg.message ?? "");
                        Debug.Log($"[SumoWS] 场景已切换: {ScenarioLabel}");
                        break;

                    case "llm_alert":
                        var alert = LlmAlertData.FromJson(raw);
                        if (alert != null && !string.IsNullOrEmpty(alert.junction))
                        {
                            OnLlmAlertReceived?.Invoke(alert);
                        }
                        break;

                    case "llm_alert_error":
                        OnLlmAlertError?.Invoke(msg.message ?? "云脑分析失败");
                        break;
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[SumoWS] 解析消息失败: {e.Message}");
            }
        }

        /// <summary>发送任意 JSON 指令（主线程调用）</summary>
        public async void SendRaw(string rawJson)
        {
            if (!IsConnected)
            {
                Debug.LogWarning("[SumoWS] 未连接，无法发送");
                return;
            }

            var bytes = Encoding.UTF8.GetBytes(rawJson);
            try
            {
                await _ws.SendAsync(bytes, WebSocketMessageType.Text, true, _cts.Token);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[SumoWS] 发送失败: {e.Message}");
            }
        }

        /// <summary>发送切换场景指令</summary>
        public void SwitchScenario(string scenario)
        {
            if (!IsConnected)
            {
                Debug.LogWarning("[SumoWS] 未连接，无法切换场景");
                return;
            }

            SendRaw($"{{\"type\":\"switch_scenario\",\"scenario\":\"{scenario}\"}}");
            Debug.Log($"[SumoWS] 已发送切换场景指令: {scenario}");
        }

        /// <summary>请求一次云端 LLM 诊断；junction 为空时由后端规则自动选最异常路口</summary>
        public void RequestLlmAlert(string junction = null)
        {
            var json = junction == null
                ? "{\"type\":\"request_llm_alert\"}"
                : $"{{\"type\":\"request_llm_alert\",\"junction\":\"{junction}\"}}";
            SendRaw(json);
        }

        void OnDestroy()
        {
            _cts?.Cancel();
            if (_ws != null)
            {
                try
                {
                    if (_ws.State == WebSocketState.Open)
                    {
                        _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Client closing", CancellationToken.None).Wait(1000);
                    }
                }
                catch { }
                _ws.Dispose();
            }
        }

        // ── JSON 消息结构（用于解析头部） ──
        [Serializable]
        class WsMessage
        {
            public string type;
            public string scenario;
            public string scenario_label;
            public string message;
        }
    }
}
