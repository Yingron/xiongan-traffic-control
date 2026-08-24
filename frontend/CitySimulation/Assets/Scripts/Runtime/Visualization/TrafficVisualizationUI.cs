using UnityEngine;
using UnityEngine.UI;

namespace CitySimulation.Runtime.Visualization
{
    /// <summary>
    /// 可视化系统主控 UI — 场景切换按钮 + 实时指标仪表盘。
    /// 自动创建 UI 元素，无需手动搭建 Canvas。
    /// </summary>
    [RequireComponent(typeof(SumoWebSocketClient))]
    [RequireComponent(typeof(SumoVisualizationBridge))]
    public class TrafficVisualizationUI : MonoBehaviour
    {
        SumoWebSocketClient _wsClient;
        SumoVisualizationBridge _bridge;
        Font _uiFont;

        // ── UI 元素 ──
        Text _statusText;
        Text _scenarioText;
        Text _metricsText;
        Text _vehicleCountText;
        Button _morningBtn;
        Button _eveningBtn;
        Button _flatBtn;

        // ── 颜色 ──
        static readonly Color ColorConnected = new Color(0.2f, 0.8f, 0.2f);
        static readonly Color ColorDisconnected = new Color(0.8f, 0.2f, 0.2f);
        static readonly Color ColorBtnActive = new Color(0.3f, 0.6f, 1f);
        static readonly Color ColorBtnNormal = new Color(0.4f, 0.4f, 0.4f, 0.8f);

        void Start()
        {
            // 优先加载中文字体（Resources/Fonts/simhei.ttf），避免中文显示为方块
            _uiFont = Resources.Load<Font>("Fonts/simhei");
            if (_uiFont == null)
            {
                _uiFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            }

            _wsClient = GetComponent<SumoWebSocketClient>();
            _bridge = GetComponent<SumoVisualizationBridge>();
            BuildUI();

            _wsClient.OnConnectionChanged += OnConnectionChanged;
            _wsClient.OnScenarioSwitched += OnScenarioSwitched;
        }

        void Update()
        {
            UpdateMetricsDisplay();
        }

        // ── UI 构建 ──

        void BuildUI()
        {
            // Canvas
            var canvasGo = new GameObject("VisualizationCanvas");
            canvasGo.transform.SetParent(transform, false);
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvasGo.AddComponent<CanvasScaler>().uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            canvasGo.GetComponent<CanvasScaler>().referenceResolution = new Vector2(1920, 1080);
            canvasGo.AddComponent<GraphicRaycaster>();

            // ── 左上：连接状态 + 场景信息 ──
            _statusText = CreateText(canvasGo.transform, new Vector2(20, -20), 300, 30,
                "正在连接...", 14, TextAnchor.UpperLeft);
            _statusText.color = ColorDisconnected;

            _scenarioText = CreateText(canvasGo.transform, new Vector2(20, -50), 300, 30,
                "场景: --", 16, TextAnchor.UpperLeft);
            _scenarioText.fontStyle = FontStyle.Bold;

            // ── 顶部中央：平台标题 ──
            var titleGo = new GameObject("Title");
            titleGo.transform.SetParent(canvasGo.transform, false);
            var titleRt = titleGo.AddComponent<RectTransform>();
            titleRt.anchorMin = titleRt.anchorMax = new Vector2(0.5f, 1f);
            titleRt.pivot = new Vector2(0.5f, 1f);
            titleRt.anchoredPosition = new Vector2(0, -14);
            titleRt.sizeDelta = new Vector2(900, 38);
            var titleImg = titleGo.AddComponent<Image>();
            titleImg.color = new Color(0, 0, 0, 0.35f);
            titleImg.raycastTarget = false;
            // Image 与 Text 都是 Graphic，不能挂在同一个 GameObject 上。
            // 标题文本作为背景面板的子物体，避免启动时 UI 初始化空引用。
            var titleTextGo = new GameObject("TitleText");
            titleTextGo.transform.SetParent(titleGo.transform, false);
            var titleTextRt = titleTextGo.AddComponent<RectTransform>();
            titleTextRt.anchorMin = Vector2.zero;
            titleTextRt.anchorMax = Vector2.one;
            titleTextRt.offsetMin = Vector2.zero;
            titleTextRt.offsetMax = Vector2.zero;
            var title = titleTextGo.AddComponent<Text>();
            title.font = _uiFont;
            title.text = "雄安新区车路云一体化协同管控平台";
            title.fontSize = 22;
            title.fontStyle = FontStyle.Bold;
            title.alignment = TextAnchor.MiddleCenter;
            title.color = new Color(1f, 1f, 1f, 0.95f);
            title.raycastTarget = false;

            // ── 右上：场景切换按钮 ──
            _morningBtn = CreateButton(canvasGo.transform, new Vector2(-340, -20), 100, 40, "早高峰", () => SwitchScene("real_peak"));
            _eveningBtn = CreateButton(canvasGo.transform, new Vector2(-230, -20), 100, 40, "晚高峰", () => SwitchScene("real_evening"));
            _flatBtn = CreateButton(canvasGo.transform, new Vector2(-120, -20), 100, 40, "平峰", () => SwitchScene("real_offpeak"));

            // ── 左下：指标面板 ──
            var panelGo = CreatePanel(canvasGo.transform, new Vector2(20, -180), 300, 150);
            _metricsText = CreateText(panelGo.transform, new Vector2(10, -10), 280, 130,
                "等待数据...", 13, TextAnchor.UpperLeft);
            _metricsText.color = new Color(0.9f, 0.9f, 0.9f);

            // ── 右下：车辆数量 ──
            _vehicleCountText = CreateText(canvasGo.transform, new Vector2(-120, -40), 100, 30,
                "车辆: 0", 14, TextAnchor.UpperLeft);
            _vehicleCountText.color = Color.cyan;
        }

        Text CreateText(Transform parent, Vector2 pos, float w, float h, string content, int fontSize, TextAnchor anchor)
        {
            var go = new GameObject("Text");
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = new Vector2(0, 1); // 左上角
            rt.pivot = new Vector2(0, 1);
            rt.anchoredPosition = pos;
            rt.sizeDelta = new Vector2(w, h);
            var text = go.AddComponent<Text>();
            text.font = _uiFont;
            text.text = content;
            text.fontSize = fontSize;
            text.alignment = anchor;
            text.raycastTarget = false;
            return text;
        }

        Button CreateButton(Transform parent, Vector2 pos, float w, float h, string label, UnityEngine.Events.UnityAction onClick)
        {
            var go = new GameObject("Btn_" + label);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = new Vector2(1, 1); // 右上角
            rt.pivot = new Vector2(0, 1);
            rt.anchoredPosition = pos;
            rt.sizeDelta = new Vector2(w, h);

            var img = go.AddComponent<Image>();
            img.color = ColorBtnNormal;

            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;
            btn.onClick.AddListener(onClick);

            // 按钮文字
            var textGo = new GameObject("Label");
            textGo.transform.SetParent(go.transform, false);
            var textRt = textGo.AddComponent<RectTransform>();
            textRt.anchorMin = Vector2.zero;
            textRt.anchorMax = Vector2.one;
            textRt.pivot = new Vector2(0.5f, 0.5f);
            textRt.sizeDelta = Vector2.zero;
            var text = textGo.AddComponent<Text>();
            text.font = _uiFont;
            text.text = label;
            text.fontSize = 14;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;

            return btn;
        }

        GameObject CreatePanel(Transform parent, Vector2 pos, float w, float h)
        {
            var go = new GameObject("Panel");
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = new Vector2(0, 0); // 左下角
            rt.pivot = new Vector2(0, 0);
            rt.anchoredPosition = new Vector2(pos.x, -pos.y - h);
            rt.sizeDelta = new Vector2(w, h);
            var img = go.AddComponent<Image>();
            img.color = new Color(0.1f, 0.1f, 0.15f, 0.85f);
            return go;
        }

        // ── 事件处理 ──

        void OnConnectionChanged(bool connected)
        {
            if (_statusText != null)
            {
                _statusText.text = connected ? "● 已连接" : "○ 未连接 — 重试中...";
                _statusText.color = connected ? ColorConnected : ColorDisconnected;
            }
        }

        void OnScenarioSwitched(string scenario, string message)
        {
            UpdateScenarioDisplay(scenario);
        }

        void UpdateScenarioDisplay(string scenario)
        {
            var labels = new System.Collections.Generic.Dictionary<string, string>
            {
                {"real_peak", "早高峰"}, {"real_evening", "晚高峰"}, {"real_offpeak", "平峰"}
            };
            var label = labels.TryGetValue(scenario, out var l) ? l : scenario;
            if (_scenarioText != null)
            {
                _scenarioText.text = $"场景: {label}";
            }

            // 更新按钮高亮
            SetButtonColor(_morningBtn, scenario == "real_peak");
            SetButtonColor(_eveningBtn, scenario == "real_evening");
            SetButtonColor(_flatBtn, scenario == "real_offpeak");
        }

        void SetButtonColor(Button btn, bool active)
        {
            if (btn == null) return;
            var img = btn.GetComponent<Image>();
            if (img != null)
            {
                img.color = active ? ColorBtnActive : ColorBtnNormal;
            }
        }

        void SwitchScene(string scenario)
        {
            if (_wsClient != null)
            {
                _wsClient.SwitchScenario(scenario);
                UpdateScenarioDisplay(scenario);
            }
        }

        // ── 指标更新 ──

        void UpdateMetricsDisplay()
        {
            if (_bridge == null || _bridge.CurrentMetrics == null) return;

            var m = _bridge.CurrentMetrics;

            if (_metricsText != null)
            {
                _metricsText.text =
                    $"仿真时间: {m.simulation_time:F0}s\n" +
                    $"车辆总数: {m.vehicle_count}\n" +
                    $"平均排队: {m.avg_queue:F1} 辆/路口\n" +
                    $"平均等待: {m.avg_wait:F1}s\n" +
                    $"平均车速: {m.avg_speed:F1} m/s\n" +
                    $"已到达: {m.total_arrived}\n" +
                    $"已发车: {m.total_departed}";
            }

            if (_vehicleCountText != null)
            {
                _vehicleCountText.text = $"渲染车辆: {_bridge.ActiveVehicleCount}";
            }
        }

        // ── 连接状态同步 ──
        void LateUpdate()
        {
            if (_wsClient != null && !string.IsNullOrEmpty(_wsClient.ScenarioLabel))
            {
                UpdateScenarioDisplay(_wsClient.CurrentScenario);
            }
        }

        void OnDestroy()
        {
            if (_wsClient != null)
            {
                _wsClient.OnConnectionChanged -= OnConnectionChanged;
                _wsClient.OnScenarioSwitched -= OnScenarioSwitched;
            }
        }
    }
}
