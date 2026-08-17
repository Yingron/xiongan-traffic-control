using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.Networking;

namespace CitySimulation.Runtime.Dqn
{
    /// <summary>
    /// REST client for the real 30-junction control session.  It deliberately
    /// talks to port 8000 (not the independent port-8765 visual snapshot feed):
    /// state -> DQN predict -> atomic 30-action submit -> next state.
    /// </summary>
    [DisallowMultipleComponent]
    public class DqnControlClient : MonoBehaviour
    {
        [Header("30 路口 DQN API")]
        public string apiBaseUrl = "http://127.0.0.1:8000/api/v1";
        public string scenario = "real_offpeak";
        public string modelId = "shared-dqn-real-offpeak-masked-1m-v1";
        public bool autoStartSession = true;
        public bool autoRun = true;
        [Range(1, 60)] public int stepSeconds = 5;
        [Min(0.05f)] public float requestIntervalSeconds = 0.25f;

        public bool IsRunning { get; private set; }
        public string SessionId { get; private set; }
        public string LastError { get; private set; }
        public ApiStateSnapshot CurrentState { get; private set; }
        public int[][] CurrentActionMasks { get; private set; }
        public IReadOnlyDictionary<string, int> LastActions => _lastActions;

        public event Action<ApiStateSnapshot> OnStateUpdated;
        public event Action<int[][]> OnMasksUpdated;
        public event Action<IReadOnlyDictionary<string, int>> OnActionsPredicted;
        public event Action<string> OnStatusChanged;

        readonly Dictionary<string, int> _lastActions = new Dictionary<string, int>();
        Coroutine _loop;

        void Start()
        {
            if (autoStartSession) StartControl();
        }

        public void StartControl()
        {
            if (_loop == null) _loop = StartCoroutine(ControlLoop());
        }

        public void StopControl()
        {
            if (_loop != null) StopCoroutine(_loop);
            _loop = null;
            IsRunning = false;
            var previousSessionId = SessionId;
            SessionId = null;
            if (!string.IsNullOrEmpty(previousSessionId)) StartCoroutine(StopRemoteSession(previousSessionId));
            PublishStatus("已停止 DQN 闭环，并正在关闭后端仿真会话。");
        }

        /// <summary>结束当前后端会话后，以选定车流场景重新建立 30 路口控制会话。</summary>
        public void SwitchScenario(string nextScenario)
        {
            if (string.IsNullOrEmpty(nextScenario) || nextScenario == scenario) return;
            StartCoroutine(SwitchScenarioRoutine(nextScenario));
        }

        IEnumerator SwitchScenarioRoutine(string nextScenario)
        {
            if (_loop != null) StopCoroutine(_loop);
            _loop = null;
            IsRunning = false;
            var previousSessionId = SessionId;
            SessionId = null;
            if (!string.IsNullOrEmpty(previousSessionId)) yield return StopRemoteSession(previousSessionId);

            scenario = nextScenario;
            LastError = null;
            PublishStatus($"已切换至 {scenario}，正在建立新的 30 路口后端会话。");
            _loop = StartCoroutine(ControlLoop());
        }

        IEnumerator StopRemoteSession(string sessionId)
        {
            using var request = CreateJsonRequest("POST", "/simulation/stop", $"{{\"session_id\":\"{sessionId}\"}}");
            yield return request.SendWebRequest();
            if (!RequestSucceeded(request))
            {
                Debug.LogWarning($"[DqnControl] 关闭后端会话失败：{request.downloadHandler?.text ?? request.error}");
            }
        }

        IEnumerator ControlLoop()
        {
            LastError = null;
            yield return StartSession();
            if (string.IsNullOrEmpty(SessionId))
            {
                _loop = null;
                yield break;
            }

            yield return RefreshStateAndMasks();
            if (!autoRun)
            {
                _loop = null;
                yield break;
            }

            IsRunning = true;
            PublishStatus("平峰 DQN 闭环运行中：660维状态 → 推理 → 30路口动作 → 信号执行。");
            while (IsRunning && !string.IsNullOrEmpty(SessionId))
            {
                yield return PredictAndApply();
                if (!string.IsNullOrEmpty(LastError)) break;
                yield return RefreshStateAndMasks();
                if (!string.IsNullOrEmpty(LastError)) break;
                yield return new WaitForSeconds(requestIntervalSeconds);
            }

            IsRunning = false;
            _loop = null;
        }

        IEnumerator StartSession()
        {
            var payload = $"{{\"scenario\":\"{scenario}\",\"use_gui\":false}}";
            using var request = CreateJsonRequest("POST", "/simulation/start", payload);
            yield return request.SendWebRequest();
            if (!RequestSucceeded(request))
            {
                SetError("启动 30 路口会话失败", request);
                yield break;
            }

            var response = JsonUtility.FromJson<StartSessionResponse>(request.downloadHandler.text);
            if (response == null || string.IsNullOrEmpty(response.session_id))
            {
                SetError("后端未返回 session_id", request.downloadHandler.text);
                yield break;
            }
            SessionId = response.session_id;
            PublishStatus($"已创建 {scenario} 会话：{SessionId}");
        }

        IEnumerator RefreshStateAndMasks()
        {
            if (string.IsNullOrEmpty(SessionId)) yield break;
            using (var stateRequest = UnityWebRequest.Get(Endpoint($"/simulation/state?session_id={UnityWebRequest.EscapeURL(SessionId)}")))
            {
                yield return stateRequest.SendWebRequest();
                if (!RequestSucceeded(stateRequest))
                {
                    SetError("读取 660 维状态失败", stateRequest);
                    yield break;
                }
                CurrentState = JsonUtility.FromJson<ApiStateSnapshot>(stateRequest.downloadHandler.text);
                if (CurrentState == null || CurrentState.state_vector == null || CurrentState.state_vector.Length != 660)
                {
                    SetError("后端状态维度不是 660", stateRequest.downloadHandler.text);
                    yield break;
                }
                OnStateUpdated?.Invoke(CurrentState);
            }

            using var maskRequest = UnityWebRequest.Get(Endpoint($"/simulation/action-masks?session_id={UnityWebRequest.EscapeURL(SessionId)}"));
            yield return maskRequest.SendWebRequest();
            if (!RequestSucceeded(maskRequest))
            {
                SetError("读取动作掩码失败", maskRequest);
                yield break;
            }
            var masks = JsonUtility.FromJson<ActionMasksResponse>(maskRequest.downloadHandler.text);
            var actionMasks = masks?.action_masks;
            // JsonUtility on some Unity releases does not reliably deserialize jagged arrays.
            // The API contract is exactly 30 rows of four binary values, so retain a safe fallback.
            if (actionMasks == null || actionMasks.Length != 30) actionMasks = TryParseActionMasks(maskRequest.downloadHandler.text);
            if (actionMasks == null || actionMasks.Length != 30)
            {
                SetError("后端动作掩码不是 30×4", maskRequest.downloadHandler.text);
                yield break;
            }
            CurrentActionMasks = actionMasks;
            OnMasksUpdated?.Invoke(CurrentActionMasks);
        }

        IEnumerator PredictAndApply()
        {
            var payload = $"{{\"session_id\":\"{SessionId}\",\"model_id\":\"{modelId}\",\"deterministic\":true}}";
            using (var predictRequest = CreateJsonRequest("POST", "/model/predict", payload))
            {
                yield return predictRequest.SendWebRequest();
                if (!RequestSucceeded(predictRequest))
                {
                    SetError("DQN 推理失败", predictRequest);
                    yield break;
                }
                if (!TryParseActions(predictRequest.downloadHandler.text, _lastActions))
                {
                    SetError("DQN 未返回完整的 30 路口动作", predictRequest.downloadHandler.text);
                    yield break;
                }
                OnActionsPredicted?.Invoke(_lastActions);
            }

            var actionPayload = BuildActionsPayload();
            using var actionRequest = CreateJsonRequest("POST", "/simulation/actions", actionPayload);
            yield return actionRequest.SendWebRequest();
            if (!RequestSucceeded(actionRequest))
            {
                SetError("提交 30 路口动作失败", actionRequest);
                yield break;
            }
        }

        string BuildActionsPayload()
        {
            var builder = new StringBuilder();
            builder.Append("{\"session_id\":\"").Append(SessionId).Append("\",\"expected_transition_id\":")
                .Append(CurrentState.transition_id).Append(",\"step_seconds\":").Append(stepSeconds).Append(",\"actions\":{");
            for (var index = 1; index <= 30; index++)
            {
                var id = $"J{index:00}";
                if (index > 1) builder.Append(',');
                builder.Append('\"').Append(id).Append("\":").Append(_lastActions[id]);
            }
            builder.Append("}}");
            return builder.ToString();
        }

        UnityWebRequest CreateJsonRequest(string method, string path, string payload)
        {
            var request = new UnityWebRequest(Endpoint(path), method);
            request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(payload));
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            return request;
        }

        string Endpoint(string path) => apiBaseUrl.TrimEnd('/') + path;
        static bool RequestSucceeded(UnityWebRequest request) => request.result == UnityWebRequest.Result.Success && request.responseCode >= 200 && request.responseCode < 300;

        static bool TryParseActions(string rawJson, Dictionary<string, int> destination)
        {
            destination.Clear();
            foreach (Match match in Regex.Matches(rawJson, "\\\"(J(?:0[1-9]|[12][0-9]|30))\\\"\\s*:\\s*([0-3])"))
            {
                destination[match.Groups[1].Value] = int.Parse(match.Groups[2].Value);
            }
            return destination.Count == 30;
        }

        static int[][] TryParseActionMasks(string rawJson)
        {
            var rows = new List<int[]>();
            foreach (Match match in Regex.Matches(rawJson, @"\[\s*([01])\s*,\s*([01])\s*,\s*([01])\s*,\s*([01])\s*\]"))
            {
                rows.Add(new[]
                {
                    int.Parse(match.Groups[1].Value), int.Parse(match.Groups[2].Value),
                    int.Parse(match.Groups[3].Value), int.Parse(match.Groups[4].Value)
                });
            }
            return rows.Count == 30 ? rows.ToArray() : null;
        }

        void SetError(string prefix, UnityWebRequest request) => SetError(prefix, request.downloadHandler?.text ?? request.error);
        void SetError(string prefix, string details)
        {
            LastError = $"{prefix}：{details}";
            Debug.LogError($"[DqnControl] {LastError}");
            PublishStatus(LastError);
            IsRunning = false;
        }

        void PublishStatus(string text)
        {
            Debug.Log($"[DqnControl] {text}");
            OnStatusChanged?.Invoke(text);
        }

        void OnDestroy() => StopControl();
    }

    [Serializable] public class StartSessionResponse { public string session_id; }
    [Serializable] public class ActionMasksResponse { public int transition_id; public int[][] action_masks; }
    [Serializable] public class ApiStateSnapshot
    {
        public string session_id;
        public int transition_id;
        public float simulation_time;
        public string state_layout_version;
        public string[] intersection_order;
        public float[] state_vector;
        public ApiIntersectionState[] intersections;
    }
    [Serializable] public class ApiIntersectionState { public string id; public int phase; public string phase_name; }
}
