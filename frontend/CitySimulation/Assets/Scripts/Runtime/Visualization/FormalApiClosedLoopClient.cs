using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace CitySimulation.Runtime.Visualization
{
    /// <summary>
    /// Direct Unity client for the formal C backend (port 8000).
    ///
    /// The client owns one REST/TraCI session, subscribes to its WebSocket
    /// snapshots, asks the registered DQN or ONNX model for a 30-junction
    /// decision, then posts the complete action batch back to the same session.
    /// It is intentionally separate from <see cref="SumoWebSocketClient"/>:
    /// the legacy 8765 visualization server remains available as a safe
    /// fallback, while this component exercises the documented formal contract.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class FormalApiClosedLoopClient : MonoBehaviour
    {
        const int IntersectionCount = 30;
        const int StateDimension = 660;
        const int ActionCount = 4;

        [Header("Formal API (8000)")]
        [Tooltip("FastAPI host. Do not include the /api/v1 suffix.")]
        public string apiHost = "127.0.0.1";
        [Tooltip("FastAPI port.")]
        public int apiPort = 8000;
        [Tooltip("API base path.")]
        public string apiPrefix = "/api/v1";
        [Tooltip("Run a formal REST/WebSocket session when Play starts.")]
        public bool autoStart = false;
        [Tooltip("Reconnect the formal WebSocket after a temporary disconnect.")]
        public bool autoReconnect = true;
        [Tooltip("WebSocket reconnect interval in seconds.")]
        public float reconnectInterval = 3f;
        [Tooltip("Use /edge/predict (Docker ONNX service). Disable to use /model/predict (registered SB3 DQN).")]
        public bool useEdgeInference = true;
        [Tooltip("Seconds simulated for every formal decision step.")]
        [Range(1, 60)] public int stepSeconds = 5;

        [Header("Scenario and official model mapping")]
        public string initialScenario = "real_peak";
        public string peakModelId = "shared-dqn-real-peak-masked-1m-v2";
        public string eveningModelId = "shared-dqn-real-evening-masked-1m-v1";
        public string offpeakModelId = "shared-dqn-real-offpeak-via-evening-v1";
        [Tooltip("Official ONNX model IDs used only when Use Edge Inference is enabled.")]
        public string edgePeakModelId = "edge-real-peak-onnx-v1";
        public string edgeEveningModelId = "edge-real-evening-onnx-v1";
        public string edgeOffpeakModelId = "edge-real-offpeak-via-evening-onnx-v1";
        [Tooltip("Optional deterministic SUMO seed. A negative value leaves it unset.")]
        public int seed = -1;

        public bool IsConnected => _socket != null && _socket.State == WebSocketState.Open;
        public string SessionId => _sessionId;
        public string CurrentScenario { get; private set; } = "";
        public FormalApiSnapshot LastSnapshot { get; private set; }
        public float[] LastActionMasks { get; private set; }
        public int[] LastActions { get; private set; }

        public event Action<bool> OnConnectionChanged;
        public event Action<string, string> OnScenarioSwitched;
        public event Action<FormalApiSnapshot> OnSnapshotReceived;
        public event Action<float[], int[]> OnDecisionReady;
        public event Action<string> OnProtocolError;
        /// <summary>云脑 REST 分析完成。复用 legacy 8765 链路相同的 UI 数据结构。</summary>
        public event Action<LlmAlertData> OnLlmAlertReceived;
        /// <summary>云脑 REST 分析失败；不会中断 DQN 闭环。</summary>
        public event Action<string> OnLlmAlertError;

        ClientWebSocket _socket;
        CancellationTokenSource _cts;
        readonly ConcurrentQueue<string> _messageQueue = new();
        string _sessionId = "";
        bool _connecting;
        bool _wasConnected;
        bool _decisionInFlight;
        bool _switchInFlight;
        float _reconnectTimer;
        readonly System.Collections.Generic.List<FormalApiSnapshot> _llmHistory = new();
        const int LlmHistorySize = 7;

        void Start()
        {
            if (autoStart)
            {
                StartFormalSession(initialScenario);
            }
        }

        void Update()
        {
            while (_messageQueue.TryDequeue(out var raw))
            {
                HandleWebSocketMessage(raw);
            }

            if (IsConnected)
            {
                if (!_wasConnected)
                {
                    _wasConnected = true;
                    OnConnectionChanged?.Invoke(true);
                }
                return;
            }

            if (_wasConnected)
            {
                _wasConnected = false;
                OnConnectionChanged?.Invoke(false);
            }

            if (!autoReconnect || string.IsNullOrEmpty(_sessionId) || _connecting || _switchInFlight)
            {
                return;
            }

            _reconnectTimer += Time.deltaTime;
            if (_reconnectTimer >= reconnectInterval)
            {
                _reconnectTimer = 0f;
                _ = ConnectWebSocketAsync();
            }
        }

        /// <summary>Start a new formal SUMO session. Existing sessions are stopped first.</summary>
        public void StartFormalSession(string scenario = null)
        {
            if (_switchInFlight) return;
            StartCoroutine(StartSessionRoutine(string.IsNullOrEmpty(scenario) ? initialScenario : scenario));
        }

        /// <summary>Switch the formal session and therefore also its official model mapping.</summary>
        public void SwitchScenario(string scenario)
        {
            if (string.IsNullOrEmpty(scenario) || _switchInFlight) return;
            StartFormalSession(scenario);
        }

        System.Collections.IEnumerator StartSessionRoutine(string scenario)
        {
            _switchInFlight = true;
            _decisionInFlight = false;
            LastSnapshot = null;
            LastActionMasks = null;
            LastActions = null;
            _llmHistory.Clear();

            if (!string.IsNullOrEmpty(_sessionId))
            {
                yield return StopSessionRoutine(_sessionId);
            }
            CloseWebSocket();

            var request = new FormalStartRequest
            {
                scenario = scenario,
                use_gui = false,
                include_seed = seed >= 0,
                seed = Mathf.Max(seed, 0),
            };
            var body = request.ToJson();
            using var webRequest = CreateJsonRequest("simulation/start", "POST", body);
            yield return webRequest.SendWebRequest();

            if (HasRequestError(webRequest, out var error))
            {
                ReportError($"启动 formal API 会话失败: {error}");
                _switchInFlight = false;
                yield break;
            }

            var started = JsonUtility.FromJson<FormalStartResponse>(webRequest.downloadHandler.text);
            if (started == null || string.IsNullOrEmpty(started.session_id))
            {
                ReportError("启动 formal API 会话失败：响应中没有 session_id。");
                _switchInFlight = false;
                yield break;
            }

            _sessionId = started.session_id;
            CurrentScenario = string.IsNullOrEmpty(started.scenario) ? scenario : started.scenario;
            _switchInFlight = false;
            OnScenarioSwitched?.Invoke(CurrentScenario, "已启动 formal API 会话并切换正式模型。");
            _ = ConnectWebSocketAsync();
        }

        System.Collections.IEnumerator StopSessionRoutine(string sessionId)
        {
            using var webRequest = CreateJsonRequest("simulation/stop", "POST", $"{{\"session_id\":\"{EscapeJson(sessionId)}\"}}");
            yield return webRequest.SendWebRequest();
            // A failed stop must not prevent the user from establishing a fresh
            // session. The server will return SESSION_BUSY with an actionable
            // message if an external process still owns TraCI.
            _sessionId = "";
        }

        async Task ConnectWebSocketAsync()
        {
            if (IsConnected || _connecting || string.IsNullOrEmpty(_sessionId)) return;
            _connecting = true;
            _cts?.Cancel();
            _cts = new CancellationTokenSource();

            try
            {
                _socket?.Dispose();
                _socket = new ClientWebSocket();
                var uri = new Uri($"ws://{apiHost}:{apiPort}{NormalizedPrefix}/ws");
                await _socket.ConnectAsync(uri, _cts.Token);
                Debug.Log($"[FormalApi] 已连接 → {uri}");
                SendRaw(BuildSubscribeMessage());
                _ = ReceiveLoopAsync(_cts.Token);
            }
            catch (Exception exception)
            {
                if (!_cts.IsCancellationRequested)
                {
                    ReportError($"formal API WebSocket 连接失败: {exception.Message}");
                }
            }
            finally
            {
                _connecting = false;
            }
        }

        async Task ReceiveLoopAsync(CancellationToken cancellationToken)
        {
            var buffer = new byte[65536];
            var text = new StringBuilder();
            try
            {
                while (!cancellationToken.IsCancellationRequested && _socket != null && _socket.State == WebSocketState.Open)
                {
                    var result = await _socket.ReceiveAsync(buffer, cancellationToken);
                    if (result.MessageType == WebSocketMessageType.Close) break;
                    text.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                    if (result.EndOfMessage)
                    {
                        _messageQueue.Enqueue(text.ToString());
                        text.Clear();
                    }
                }
            }
            catch (OperationCanceledException) { }
            catch (Exception exception)
            {
                if (!cancellationToken.IsCancellationRequested)
                {
                    Debug.LogWarning($"[FormalApi] WebSocket 接收异常: {exception.Message}");
                }
            }
        }

        void HandleWebSocketMessage(string raw)
        {
            var envelope = JsonUtility.FromJson<FormalEnvelope>(raw);
            if (envelope == null || string.IsNullOrEmpty(envelope.type)) return;

            switch (envelope.type)
            {
                case "subscription.confirmed":
                    Debug.Log($"[FormalApi] 订阅确认：{_sessionId}。");
                    break;
                case "simulation.state":
                    HandleSnapshot(raw);
                    break;
                case "error":
                    _decisionInFlight = false;
                    ReportError($"formal API 协议错误: {envelope.error_message ?? "未知错误"}");
                    break;
                case "heartbeat":
                    SendRaw("{\"type\":\"ping\",\"request_id\":\"unity-heartbeat\"}");
                    break;
                case "simulation.stopped":
                    _decisionInFlight = false;
                    break;
            }
        }

        void HandleSnapshot(string raw)
        {
            var snapshot = JsonUtility.FromJson<FormalApiSnapshot>(raw);
            if (!IsValidSnapshot(snapshot)) return;

            LastSnapshot = snapshot;
            RememberLlmSnapshot(snapshot);
            OnSnapshotReceived?.Invoke(snapshot);
            if (!_decisionInFlight && !_switchInFlight)
            {
                StartCoroutine(PredictAndApplyRoutine(snapshot));
            }
        }

        System.Collections.IEnumerator PredictAndApplyRoutine(FormalApiSnapshot snapshot)
        {
            _decisionInFlight = true;
            var modelId = useEdgeInference ? EdgeModelIdForScenario(CurrentScenario) : ModelIdForScenario(CurrentScenario);
            if (string.IsNullOrEmpty(modelId))
            {
                _decisionInFlight = false;
                ReportError($"未配置场景 {CurrentScenario} 的正式模型 ID。");
                yield break;
            }

            var predictionBody = $"{{\"session_id\":\"{EscapeJson(_sessionId)}\",\"model_id\":\"{EscapeJson(modelId)}\",\"deterministic\":true}}";
            using var predictionRequest = CreateJsonRequest(useEdgeInference ? "edge/predict" : "model/predict", "POST", predictionBody);
            yield return predictionRequest.SendWebRequest();
            if (HasRequestError(predictionRequest, out var predictionError))
            {
                _decisionInFlight = false;
                ReportError($"formal DQN 推理失败: {predictionError}");
                yield break;
            }

            var prediction = JsonUtility.FromJson<FormalPrediction>(predictionRequest.downloadHandler.text);
            if (!IsValidPrediction(prediction, snapshot.transition_id))
            {
                _decisionInFlight = false;
                yield break;
            }
            LastActionMasks = prediction.action_masks_flat;
            LastActions = prediction.actions_ordered;
            OnDecisionReady?.Invoke(LastActionMasks, LastActions);

            var actionsBody = BuildActionsRequest(prediction.transition_id, prediction.actions_ordered);
            using var actionsRequest = CreateJsonRequest("simulation/actions", "POST", actionsBody);
            yield return actionsRequest.SendWebRequest();
            if (HasRequestError(actionsRequest, out var actionError))
            {
                _decisionInFlight = false;
                ReportError($"formal 动作回传失败: {actionError}");
                yield break;
            }

            _decisionInFlight = false;
            // The API broadcasts the new state to this WebSocket subscription.
            // No local simulation step is ever fabricated on the Unity side.
        }

        /// <summary>
        /// Ask the C-backend cloud-brain endpoint to diagnose one junction from
        /// the current formal session. If no junction is supplied, the client
        /// selects the highest current normalized queue pressure. This call is
        /// diagnostic-only: it never changes the DQN action or SUMO phase.
        /// </summary>
        public void RequestLlmAlert(string junction = null)
        {
            if (LastSnapshot == null || string.IsNullOrEmpty(_sessionId))
            {
                OnLlmAlertError?.Invoke("尚未收到正式后端状态，暂不能进行云脑诊断。");
                return;
            }
            StartCoroutine(RequestLlmAlertRoutine(junction));
        }

        System.Collections.IEnumerator RequestLlmAlertRoutine(string requestedJunction)
        {
            var junction = NormalizeOrSelectLlmJunction(requestedJunction);
            var prompt = BuildLlmPrompt(junction);
            var body = $"{{\"text\":\"{EscapeJson(prompt)}\",\"junction\":\"{junction}\"}}";
            using var request = CreateJsonRequest("llm/analyze", "POST", body);
            yield return request.SendWebRequest();
            if (HasRequestError(request, out var error))
            {
                OnLlmAlertError?.Invoke(error);
                yield break;
            }

            var alert = LlmAlertData.FromJson(request.downloadHandler.text);
            if (alert == null)
            {
                OnLlmAlertError?.Invoke("云脑响应无法解析。");
                yield break;
            }
            alert.junction = string.IsNullOrEmpty(alert.junction) ? junction : alert.junction;
            alert.scenario = CurrentScenario;
            alert.sim_time = LastSnapshot == null ? 0f : LastSnapshot.simulation_time;
            alert.sim_clock = $"仿真第 {alert.sim_time:F0} 秒";
            OnLlmAlertReceived?.Invoke(alert);
        }

        void RememberLlmSnapshot(FormalApiSnapshot snapshot)
        {
            _llmHistory.Add(snapshot);
            while (_llmHistory.Count > LlmHistorySize)
            {
                _llmHistory.RemoveAt(0);
            }
        }

        string NormalizeOrSelectLlmJunction(string junction)
        {
            if (!string.IsNullOrEmpty(junction) &&
                System.Text.RegularExpressions.Regex.IsMatch(junction, "^J(0[1-9]|[12][0-9]|30)$"))
            {
                return junction;
            }

            var latest = LastSnapshot;
            var selectedIndex = 0;
            var highestPressure = float.NegativeInfinity;
            for (var index = 0; index < IntersectionCount; index++)
            {
                var offset = index * 22;
                var pressure = latest.state_vector[offset] + latest.state_vector[offset + 1]
                    + latest.state_vector[offset + 2] + latest.state_vector[offset + 3]
                    + latest.state_vector[offset + 8] + latest.state_vector[offset + 9]
                    + latest.state_vector[offset + 10] + latest.state_vector[offset + 11];
                if (pressure > highestPressure)
                {
                    highestPressure = pressure;
                    selectedIndex = index;
                }
            }
            return $"J{selectedIndex + 1:D2}";
        }

        string BuildLlmPrompt(string junction)
        {
            var index = int.Parse(junction.Substring(1)) - 1;
            var scenarioLabel = CurrentScenario switch
            {
                "real_peak" => "真实早高峰",
                "real_offpeak" => "真实平峰",
                "real_evening" => "真实晚高峰",
                _ => CurrentScenario,
            };
            var samples = _llmHistory.Count > 0 ? _llmHistory : new System.Collections.Generic.List<FormalApiSnapshot> { LastSnapshot };
            var builder = new StringBuilder();
            builder.Append("【场景】").Append(scenarioLabel).Append("（正式后端实时状态）\n");
            builder.Append("【路口 ").Append(junction).Append("】最近 ")
                .Append(Mathf.Max(0, samples.Count - 1) * stepSeconds).Append(" 秒交通状态：\n");
            foreach (var sample in samples)
            {
                var offset = index * 22;
                var phase = sample.intersections != null && sample.intersections.Length > index
                    ? sample.intersections[index].phase_name
                    : "未知相位";
                builder.Append("  仿真第 ").Append(sample.simulation_time.ToString("F0"))
                    .Append(" 秒 | 相位:").Append(phase).Append(" | ");
                AppendDirection(builder, "北", sample.state_vector, offset, 0);
                AppendDirection(builder, "南", sample.state_vector, offset, 1);
                AppendDirection(builder, "东", sample.state_vector, offset, 2);
                AppendDirection(builder, "西", sample.state_vector, offset, 3, true);
            }
            builder.Append("【问题】请判断该路口当前运行状态属于正常、拥堵、溢出或事件，")
                .Append("并根据排队、平均等待、占有率和当前相位给出中文信号管控建议。")
                .Append("只输出 JSON：{\"event\":\"正常|拥堵|溢出|事件\",\"confidence\":0.0,\"advice\":\"中文管控建议\"}。");
            return builder.ToString();
        }

        static void AppendDirection(StringBuilder builder, string direction, float[] state, int offset, int directionIndex, bool last = false)
        {
            // 660 维契约的队列和等待分别以 15 辆、120 秒归一化；这里只为
            // 云脑展示还原单位，控制器始终使用原始归一化状态，不受该文本影响。
            var queue = state[offset + directionIndex] * 15f;
            var wait = state[offset + 4 + directionIndex] * 120f;
            var occupancy = state[offset + 8 + directionIndex];
            builder.Append(direction).Append("向:排队").Append(queue.ToString("F0"))
                .Append("辆 平均等待").Append(wait.ToString("F0"))
                .Append("秒 占有率").Append(occupancy.ToString("F2"));
            builder.Append(last ? "\n" : " | ");
        }

        bool IsValidSnapshot(FormalApiSnapshot snapshot)
        {
            if (snapshot == null || snapshot.state_vector == null || snapshot.state_vector.Length != StateDimension ||
                snapshot.intersections == null || snapshot.intersections.Length != IntersectionCount)
            {
                ReportError("formal API 快照不满足 30 路口/660 维契约，已拒绝渲染和推理。");
                return false;
            }
            if (snapshot.visualization == null || snapshot.visualization.traffic_lights == null ||
                snapshot.visualization.traffic_lights.Length != IntersectionCount)
            {
                ReportError("formal API 快照缺少 30 盏信号灯可视化数据，已拒绝渲染和推理。");
                return false;
            }
            return true;
        }

        bool IsValidPrediction(FormalPrediction prediction, int expectedTransitionId)
        {
            if (prediction == null || prediction.transition_id != expectedTransitionId ||
                prediction.actions_ordered == null || prediction.actions_ordered.Length != IntersectionCount ||
                prediction.action_masks_flat == null || prediction.action_masks_flat.Length != IntersectionCount * ActionCount)
            {
                ReportError("formal DQN 响应不满足 30×4 掩码或 30 动作契约，已拒绝执行。");
                return false;
            }
            foreach (var action in prediction.actions_ordered)
            {
                if (action < 0 || action >= ActionCount)
                {
                    ReportError("formal DQN 响应含非法相位动作，已拒绝执行。");
                    return false;
                }
            }
            return true;
        }

        string ModelIdForScenario(string scenario)
        {
            return scenario switch
            {
                "real_peak" => peakModelId,
                "real_evening" => eveningModelId,
                "real_offpeak" => offpeakModelId,
                _ => "",
            };
        }

        string EdgeModelIdForScenario(string scenario)
        {
            return scenario switch
            {
                "real_peak" => edgePeakModelId,
                "real_evening" => edgeEveningModelId,
                "real_offpeak" => edgeOffpeakModelId,
                _ => "",
            };
        }

        string BuildSubscribeMessage()
        {
            return $"{{\"type\":\"subscribe\",\"request_id\":\"unity-subscribe\",\"session_id\":\"{EscapeJson(_sessionId)}\",\"channels\":[\"state\",\"reward\"]}}";
        }

        string BuildActionsRequest(int transitionId, int[] actions)
        {
            var builder = new StringBuilder();
            builder.Append("{\"session_id\":\"").Append(EscapeJson(_sessionId))
                .Append("\",\"expected_transition_id\":").Append(transitionId)
                .Append(",\"actions\":{");
            for (var index = 0; index < IntersectionCount; index++)
            {
                if (index > 0) builder.Append(',');
                builder.Append("\"J").Append((index + 1).ToString("D2")).Append("\":").Append(actions[index]);
            }
            builder.Append("},\"step_seconds\":").Append(stepSeconds).Append('}');
            return builder.ToString();
        }

        UnityWebRequest CreateJsonRequest(string endpoint, string method, string body)
        {
            var request = new UnityWebRequest($"{HttpBaseUrl}/{endpoint}", method);
            request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            return request;
        }

        bool HasRequestError(UnityWebRequest request, out string error)
        {
            if (request.result == UnityWebRequest.Result.Success)
            {
                error = "";
                return false;
            }
            error = string.IsNullOrEmpty(request.downloadHandler?.text) ? request.error : request.downloadHandler.text;
            return true;
        }

        void SendRaw(string rawJson)
        {
            if (!IsConnected || _cts == null) return;
            _ = SendRawAsync(rawJson, _cts.Token);
        }

        async Task SendRawAsync(string rawJson, CancellationToken cancellationToken)
        {
            try
            {
                var bytes = Encoding.UTF8.GetBytes(rawJson);
                await _socket.SendAsync(bytes, WebSocketMessageType.Text, true, cancellationToken);
            }
            catch (Exception exception)
            {
                if (!cancellationToken.IsCancellationRequested)
                {
                    ReportError($"formal API WebSocket 发送失败: {exception.Message}");
                }
            }
        }

        void CloseWebSocket()
        {
            _cts?.Cancel();
            if (_socket != null)
            {
                try { _socket.Dispose(); }
                catch { }
                _socket = null;
            }
        }

        void ReportError(string message)
        {
            Debug.LogWarning($"[FormalApi] {message}");
            OnProtocolError?.Invoke(message);
        }

        string NormalizedPrefix => string.IsNullOrWhiteSpace(apiPrefix)
            ? "/api/v1"
            : (apiPrefix.StartsWith("/") ? apiPrefix : "/" + apiPrefix).TrimEnd('/');
        string HttpBaseUrl => $"http://{apiHost}:{apiPort}{NormalizedPrefix}";

        static string EscapeJson(string value)
        {
            return (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        void OnDestroy()
        {
            CloseWebSocket();
        }

        [Serializable]
        class FormalEnvelope
        {
            public string type;
            public string message;
            public FormalError error;
            public string error_message => error == null ? message : error.message;
        }

        [Serializable]
        class FormalError { public string code; public string message; }

        [Serializable]
        class FormalStartResponse { public string session_id; public string scenario; }

        class FormalStartRequest
        {
            public string scenario;
            public bool use_gui;
            public bool include_seed;
            public int seed;

            public string ToJson()
            {
                return include_seed
                    ? $"{{\"scenario\":\"{FormalApiClosedLoopClient.EscapeJson(scenario)}\",\"use_gui\":false,\"seed\":{seed}}}"
                    : $"{{\"scenario\":\"{FormalApiClosedLoopClient.EscapeJson(scenario)}\",\"use_gui\":false}}";
            }
        }
    }

    /// <summary>Direct 8000 WebSocket snapshot. The 660-D state remains the control truth.</summary>
    [Serializable]
    public class FormalApiSnapshot
    {
        public string type;
        public string session_id;
        public int transition_id;
        public float simulation_time;
        public string state_layout_version;
        public float[] state_vector;
        public FormalApiIntersection[] intersections;
        public FormalApiVisualization visualization;
        public float global_reward;
    }

    [Serializable]
    public class FormalApiIntersection
    {
        public string id;
        public int state_offset;
        public int phase;
        public string phase_name;
    }

    [Serializable]
    public class FormalApiVisualization
    {
        public SimTrafficLight[] traffic_lights;
        public SimVehicle[] vehicles;
        public SimMetrics metrics;
    }

    [Serializable]
    public class FormalPrediction
    {
        public string session_id;
        public int transition_id;
        public string model_id;
        public string model_contract_version;
        public float[] action_masks_flat;
        public int[] action_masks_shape;
        public int[] actions_ordered;
    }
}
