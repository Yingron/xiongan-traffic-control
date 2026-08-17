using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace CitySimulation.Runtime.Dqn
{
    /// <summary>Runtime dashboard for the API's real state, masks and DQN actions.</summary>
    [RequireComponent(typeof(DqnControlClient))]
    [DisallowMultipleComponent]
    public class DqnDashboardUI : MonoBehaviour
    {
        DqnControlClient _client;
        Text _headline;
        Text _body;
        Button _startButton;
        Button _stopButton;
        string _status = "等待 DQN API 连接...";
        ApiStateSnapshot _state;
        int[][] _masks;

        void Start()
        {
            _client = GetComponent<DqnControlClient>();
            BuildUi();
            _client.OnStatusChanged += OnStatus;
            _client.OnStateUpdated += state => { _state = state; Refresh(); };
            _client.OnMasksUpdated += masks => { _masks = masks; Refresh(); };
            _client.OnActionsPredicted += _ => Refresh();
        }

        void OnDestroy()
        {
            if (_client == null) return;
            _client.OnStatusChanged -= OnStatus;
        }

        void OnStatus(string status) { _status = status; Refresh(); }

        void BuildUi()
        {
            var canvasGo = new GameObject("DqnDashboardCanvas");
            canvasGo.transform.SetParent(transform, false);
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920, 1080);
            canvasGo.AddComponent<GraphicRaycaster>();

            var panel = CreatePanel(canvasGo.transform, new Vector2(-24, -145), new Vector2(470, 305));
            _headline = CreateText(panel.transform, new Vector2(16, -14), new Vector2(438, 28), 17, FontStyle.Bold, Color.cyan);
            _body = CreateText(panel.transform, new Vector2(16, -48), new Vector2(438, 180), 13, FontStyle.Normal, new Color(0.94f, 0.96f, 1f));
            _startButton = CreateButton(panel.transform, new Vector2(16, 14), "启动闭环", () => _client.StartControl());
            _stopButton = CreateButton(panel.transform, new Vector2(138, 14), "停止闭环", () => _client.StopControl());
            CreateButton(panel.transform, new Vector2(260, 14), "早高峰", () => _client.SwitchScenario("real_peak"));
            CreateButton(panel.transform, new Vector2(16, 48), "平峰", () => _client.SwitchScenario("real_offpeak"));
            CreateButton(panel.transform, new Vector2(138, 48), "晚高峰", () => _client.SwitchScenario("real_evening"));
            Refresh();
        }

        void Refresh()
        {
            if (_headline == null) return;
            _headline.text = _client != null && _client.IsRunning ? "● 30路口 DQN 实时控制" : "○ 30路口 DQN 控制面板";
            if (_state == null)
            {
                _body.text = _status;
                return;
            }

            var busiestIndex = 0;
            var biggestQueue = -1f;
            var totalQueue = 0f;
            var totalWait = 0f;
            for (var intersection = 0; intersection < 30; intersection++)
            {
                var offset = intersection * 22;
                var queue = 0f;
                for (var direction = 0; direction < 4; direction++)
                {
                    queue += _state.state_vector[offset + direction];
                    totalWait += _state.state_vector[offset + 4 + direction];
                }
                totalQueue += queue;
                if (queue > biggestQueue) { biggestQueue = queue; busiestIndex = intersection; }
            }

            var busiestId = $"J{busiestIndex + 1:00}";
            var action = _client.LastActions.TryGetValue(busiestId, out var actionIndex) ? ActionLabel(actionIndex) : "等待推理";
            var mask = MaskLabel(busiestIndex);
            _body.text =
                $"场景：{ScenarioLabel(_client.scenario)}\n" +
                $"会话：{ShortSession(_state.session_id)}   仿真：{_state.simulation_time:F0}s   转换：{_state.transition_id}\n" +
                $"真实状态：{_state.state_vector.Length} 维（30 × 22）\n" +
                $"归一化平均排队：{totalQueue / 30f:F3}   平均等待：{totalWait / 120f:F3}\n" +
                $"重点路口：{busiestId}，队列强度 {biggestQueue:F3}\n" +
                $"DQN 动作：{action}\n" +
                $"动作掩码 [NS直, NS左, EW直, EW左]：{mask}\n" +
                $"状态：{_status}";
        }

        string MaskLabel(int index)
        {
            if (_masks == null || index >= _masks.Length || _masks[index] == null || _masks[index].Length != 4) return "等待后端";
            return $"[{_masks[index][0]}, {_masks[index][1]}, {_masks[index][2]}, {_masks[index][3]}]";
        }

        static string ActionLabel(int action) => action switch
        {
            0 => "0 · 南北直行", 1 => "1 · 南北左转", 2 => "2 · 东西直行", 3 => "3 · 东西左转", _ => "无效动作"
        };
        static string ScenarioLabel(string value) => value switch
        {
            "real_peak" => "早高峰（real_peak）",
            "real_evening" => "晚高峰（real_evening）",
            _ => "平峰（real_offpeak）"
        };
        static string ShortSession(string id) => string.IsNullOrEmpty(id) ? "--" : id.Substring(0, Mathf.Min(id.Length, 14));

        static GameObject CreatePanel(Transform parent, Vector2 anchoredPosition, Vector2 size)
        {
            var go = new GameObject("DqnDashboardPanel");
            go.transform.SetParent(parent, false);
            var rect = go.AddComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = new Vector2(1, 1);
            rect.pivot = new Vector2(1, 1);
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = size;
            go.AddComponent<Image>().color = new Color(0.035f, 0.07f, 0.12f, 0.92f);
            return go;
        }

        static Text CreateText(Transform parent, Vector2 position, Vector2 size, int fontSize, FontStyle style, Color color)
        {
            var go = new GameObject("Text");
            go.transform.SetParent(parent, false);
            var rect = go.AddComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = new Vector2(0, 1);
            rect.pivot = new Vector2(0, 1);
            rect.anchoredPosition = position;
            rect.sizeDelta = size;
            var text = go.AddComponent<Text>();
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = fontSize;
            text.fontStyle = style;
            text.color = color;
            text.alignment = TextAnchor.UpperLeft;
            text.raycastTarget = false;
            return text;
        }

        static Button CreateButton(Transform parent, Vector2 position, string label, UnityEngine.Events.UnityAction onClick)
        {
            var go = new GameObject(label);
            go.transform.SetParent(parent, false);
            var rect = go.AddComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = new Vector2(0, 0);
            rect.pivot = new Vector2(0, 0);
            rect.anchoredPosition = position;
            rect.sizeDelta = new Vector2(110, 30);
            go.AddComponent<Image>().color = new Color(0.13f, 0.42f, 0.72f, 1f);
            var button = go.AddComponent<Button>();
            button.onClick.AddListener(onClick);
            var text = CreateText(go.transform, new Vector2(0, 0), new Vector2(110, 30), 12, FontStyle.Bold, Color.white);
            text.alignment = TextAnchor.MiddleCenter;
            return button;
        }
    }
}
