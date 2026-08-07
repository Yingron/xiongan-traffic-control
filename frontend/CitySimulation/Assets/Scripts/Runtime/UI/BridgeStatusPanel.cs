using CitySimulation.Global;
using CitySimulation.Runtime.Simulation;
using UnityEngine;
using UnityEngine.UI;

namespace CitySimulation.Runtime.UI
{
    /// <summary>
    /// 后端连接状态面板（Runtime）。
    /// 挂载到任意 GameObject 上即可显示 Bridge/TCP 状态并切换模式。
    /// </summary>
    [DisallowMultipleComponent]
    public class BridgeStatusPanel : MonoBehaviour
    {
        [Header("UI 引用")]
        [Tooltip("状态文本（显示连接状态、延迟、请求数）")]
        public Text statusText;

        [Tooltip("连接状态指示（颜色）")]
        public Image statusIndicator;

        [Tooltip("切换模式按钮")]
        public Button toggleButton;

        [Tooltip("模式显示文本")]
        public Text modeText;

        [Tooltip("主画布（自动创建）")]
        public Canvas canvas;

        [Header("桥接配置")]
        [Tooltip("C bridge_server 主机")]
        public string bridgeHost = "127.0.0.1";

        [Tooltip("C bridge_server 端口")]
        public int bridgePort = 5000;

        // ===================== 生命周期 =====================
        void Awake()
        {
            EnsureUI();
        }

        void Start()
        {
            // 自动初始化（如果 GameServices 尚未初始化）
            if (GameServices.BackendClinet == null)
            {
                GameServices.BridgeHost = bridgeHost;
                GameServices.BridgePort = bridgePort;
                GameServices.UseBridgeBackend = false;
                GameServices.RegisterRuntimeServices();
            }

            if (toggleButton != null)
                toggleButton.onClick.AddListener(OnToggleMode);
        }

        void Update()
        {
            UpdateDisplay();
        }

        void OnDestroy()
        {
            if (toggleButton != null)
                toggleButton.onClick.RemoveListener(OnToggleMode);
        }

        // ===================== 切换模式 =====================
        private void OnToggleMode()
        {
            var client = GameServices.BackendClinet;
            if (client == null) return;

            var newMode = client.Mode == BackendClinet.BackendMode.BridgeTcp
                ? BackendClinet.BackendMode.TestMock
                : BackendClinet.BackendMode.BridgeTcp;

            // 释放旧资源
            client.Dispose();

            // 重新初始化
            GameServices.BackendClinet = new BackendClinet();
            GameServices.BackendClinet.Initialize(newMode, bridgeHost, bridgePort);

            Debug.Log($"[BridgeStatusPanel] Switched to {newMode}");
        }

        // ===================== UI 更新 =====================
        private void UpdateDisplay()
        {
            var client = GameServices.BackendClinet;
            if (client == null || statusText == null) return;

            // 状态文本
            string stateStr = client.Mode == BackendClinet.BackendMode.BridgeTcp
                ? (client.IsBridgeConnected ? "CONNECTED" : "CONNECTING...")
                : "TEST MOCK";

            statusText.text =
                $"[Backend] {stateStr}\n" +
                $"Host: {bridgeHost}:{bridgePort}\n" +
                $"Requests: {client.TotalRequests} | Fallback: {client.FallbackCount}\n" +
                $"Latency: {client.LastLatencyMs:F1} ms";

            // 状态灯颜色
            if (statusIndicator != null)
            {
                Color c;
                switch (client.Mode)
                {
                    case BackendClinet.BackendMode.BridgeTcp:
                        c = client.IsBridgeConnected ? Color.green : Color.yellow;
                        break;
                    case BackendClinet.BackendMode.TestMock:
                    default:
                        c = Color.cyan;
                        break;
                }
                statusIndicator.color = c;
            }

            // 模式按钮文本
            if (modeText != null)
            {
                modeText.text = client.Mode == BackendClinet.BackendMode.BridgeTcp
                    ? "Switch to Test Mock"
                    : "Switch to Bridge TCP";
            }
        }

        // ===================== 自动创建 UI =====================
        private void EnsureUI()
        {
            if (canvas != null) return;

            // 创建 Canvas
            var canvasGo = new GameObject("BridgeStatusCanvas");
            canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvasGo.AddComponent<CanvasScaler>();
            canvasGo.AddComponent<GraphicRaycaster>();

            // 面板背景
            var panelGo = new GameObject("Panel");
            panelGo.transform.SetParent(canvas.transform, false);
            var panelRect = panelGo.AddComponent<RectTransform>();
            panelRect.anchorMin = new Vector2(1, 1);
            panelRect.anchorMax = new Vector2(1, 1);
            panelRect.pivot = new Vector2(1, 1);
            panelRect.sizeDelta = new Vector2(320, 140);
            panelRect.anchoredPosition = new Vector2(-20, -20);
            var panelImg = panelGo.AddComponent<Image>();
            panelImg.color = new Color(0.1f, 0.1f, 0.1f, 0.85f);

            // 状态灯
            var indicatorGo = new GameObject("StatusIndicator");
            indicatorGo.transform.SetParent(panelGo.transform, false);
            var indRect = indicatorGo.AddComponent<RectTransform>();
            indRect.anchorMin = new Vector2(0, 1);
            indRect.anchorMax = new Vector2(0, 1);
            indRect.pivot = new Vector2(0, 1);
            indRect.sizeDelta = new Vector2(16, 16);
            indRect.anchoredPosition = new Vector2(15, -15);
            statusIndicator = indicatorGo.AddComponent<Image>();
            statusIndicator.color = Color.gray;

            // 状态文本
            var textGo = new GameObject("StatusText");
            textGo.transform.SetParent(panelGo.transform, false);
            var textRect = textGo.AddComponent<RectTransform>();
            textRect.anchorMin = new Vector2(0, 0);
            textRect.anchorMax = new Vector2(1, 1);
            textRect.offsetMin = new Vector2(40, 10);
            textRect.offsetMax = new Vector2(-10, -40);
            statusText = textGo.AddComponent<Text>();
            statusText.fontSize = 12;
            statusText.color = Color.white;
            statusText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            statusText.text = "Loading...";

            // 切换按钮
            var btnGo = new GameObject("ToggleButton");
            btnGo.transform.SetParent(panelGo.transform, false);
            var btnRect = btnGo.AddComponent<RectTransform>();
            btnRect.anchorMin = new Vector2(0.5f, 0);
            btnRect.anchorMax = new Vector2(0.5f, 0);
            btnRect.pivot = new Vector2(0.5f, 0);
            btnRect.sizeDelta = new Vector2(200, 30);
            btnRect.anchoredPosition = new Vector2(0, 10);
            var btnImg = btnGo.AddComponent<Image>();
            btnImg.color = new Color(0.2f, 0.5f, 0.8f);
            toggleButton = btnGo.AddComponent<Button>();

            var btnTextGo = new GameObject("Text");
            btnTextGo.transform.SetParent(btnGo.transform, false);
            var btnTextRect = btnTextGo.AddComponent<RectTransform>();
            btnTextRect.anchorMin = Vector2.zero;
            btnTextRect.anchorMax = Vector2.one;
            btnTextRect.offsetMin = Vector2.zero;
            btnTextRect.offsetMax = Vector2.zero;
            modeText = btnTextGo.AddComponent<Text>();
            modeText.fontSize = 12;
            modeText.color = Color.white;
            modeText.alignment = TextAnchor.MiddleCenter;
            modeText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            modeText.text = "Switch to Bridge TCP";
        }
    }
}
