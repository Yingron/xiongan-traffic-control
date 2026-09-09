using System;
using UnityEngine;
using UnityEngine.UI;

namespace CitySimulation.Runtime.Visualization
{
    /// <summary>
    /// AI 云脑诊断面板（赛道 C LLM 云脑可视化）。
    ///
    /// 后端 visualization_server 周期性（默认 60s）对规则预筛的最异常路口发起
    /// llama.cpp 云脑诊断，并经 WebSocket 推送 type=llm_alert 消息；
    /// 本面板订阅 SumoWebSocketClient.OnLlmAlertReceived 展示
    /// 事件类别/置信度/中文管控建议，并提供手动"立即诊断"入口。
    ///
    /// 纯代码构建 UGUI（自动创建 Canvas），无需手动搭 UI。
    /// 由 VisualizationBootstrap 自动挂载，也可手动添加到任意 GameObject。
    /// </summary>
    public class LlmAlertPanel : MonoBehaviour
    {
        SumoWebSocketClient _wsClient;
        FormalApiClosedLoopClient _formalClient;
        Font _uiFont;

        // ── UI ──
        Text _titleText;
        Text _statusText;
        Text _eventText;
        Text _metaText;
        Text _adviceText;
        Text _updatedText;
        Button _diagnoseBtn;
        Button _j25Btn;

        // ── 状态 ──
        float _requestedAt = -1f;   // 手动诊断发起时刻（-1 表示空闲）
        float _lastAlertWallAt = -1f;
        string _scenarioLabel = "";
        bool _connected;
        float _nextFormalAutoDiagnoseAt = -1f;

        // ── 颜色 ──
        static readonly Color ColorPanel = new Color(0.08f, 0.10f, 0.14f, 0.92f);
        static readonly Color ColorHeader = new Color(0.98f, 0.85f, 0.35f);
        static readonly Color ColorConnected = new Color(0.25f, 0.85f, 0.3f);
        static readonly Color ColorDisconnected = new Color(0.8f, 0.3f, 0.3f);
        static readonly Color ColorMeta = new Color(0.72f, 0.76f, 0.8f);
        static readonly Color ColorBtnNormal = new Color(0.25f, 0.45f, 0.85f, 0.9f);
        static readonly Color ColorBtnBusy = new Color(0.45f, 0.45f, 0.5f, 0.9f);

        // 事件 → 中文/颜色
        static readonly System.Collections.Generic.Dictionary<string, Color> EventColors =
            new System.Collections.Generic.Dictionary<string, Color>
            {
                {"正常", new Color(0.35f, 0.9f, 0.4f)},
                {"拥堵", new Color(1f, 0.82f, 0.15f)},
                {"溢出", new Color(1f, 0.6f, 0.1f)},
                {"事件", new Color(1f, 0.3f, 0.3f)},
            };

        void Start()
        {
            _uiFont = Resources.Load<Font>("Fonts/simhei");
            if (_uiFont == null)
            {
                _uiFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            }

            BuildUI();

            // 优先使用 8000 正式闭环客户端。它与 DQN 使用同一 660 维快照，
            // 可直接调用 /api/v1/llm/analyze；未启用时无缝回退到 8765 推送链路。
            _formalClient = GetComponent<FormalApiClosedLoopClient>();
            if (_formalClient != null && _formalClient.enabled)
            {
                _formalClient.OnConnectionChanged += OnConnectionChanged;
                _formalClient.OnLlmAlertReceived += OnLlmAlertReceived;
                _formalClient.OnLlmAlertError += OnLlmAlertError;
                _formalClient.OnScenarioSwitched += OnScenarioSwitched;
                _formalClient.OnSnapshotReceived += OnFormalSnapshotReceived;
                _connected = _formalClient.IsConnected;
                if (_connected && _statusText != null)
                {
                    _statusText.text = "● 正式后端已连接 · 等待状态后云脑诊断…";
                    _statusText.color = ColorConnected;
                }
            }
            else
            {
                _wsClient = GetComponent<SumoWebSocketClient>();
                if (_wsClient == null)
                {
                    _wsClient = GetComponentInParent<SumoWebSocketClient>();
                }

                if (_wsClient != null)
                {
                    _wsClient.OnConnectionChanged += OnConnectionChanged;
                    _wsClient.OnLlmAlertReceived += OnLlmAlertReceived;
                    _wsClient.OnLlmAlertError += OnLlmAlertError;
                    _wsClient.OnScenarioSwitched += OnScenarioSwitched;
                    _connected = _wsClient.IsConnected;
                    if (_connected && _statusText != null)
                    {
                        _statusText.text = "● 云脑已连接 · 等待自动诊断…";
                        _statusText.color = ColorConnected;
                        // 首次连接立即请求一次诊断，避免干等一个自动周期
                        Invoke(nameof(RequestAutoDiagnose), 2f);
                    }
                }
            }
        }

        void Update()
        {
            // 手动诊断的"分析中…"倒计时恢复
            if (_requestedAt > 0 && _diagnoseBtn != null)
            {
                var elapsed = Time.time - _requestedAt;
                if (elapsed > 12f)
                {
                    SetButtonsBusy(false);
                    _requestedAt = -1f;
                }
                else if (_statusText != null)
                {
                    _statusText.text = $"◐ 云脑分析中…（约 {Mathf.Max(1, 10 - (int)elapsed)}s）";
                    _statusText.color = ColorHeader;
                }
            }

            // 8000 正式模式没有 8765 服务端的 60 秒定时器；前端仅在拿到
            // 同一会话状态后按相同节奏请求云脑，且不阻塞 DQN 闭环。
            if (_formalClient != null && _connected && _requestedAt < 0 &&
                _nextFormalAutoDiagnoseAt > 0 && Time.time >= _nextFormalAutoDiagnoseAt)
            {
                RequestAutoDiagnose();
            }
        }

        // ── UI 构建 ──

        void BuildUI()
        {
            // 独立 Canvas，sortingOrder=1 保证显示在 VisualizationCanvas 之上
            var canvasGo = new GameObject("LlmAlertCanvas");
            canvasGo.transform.SetParent(transform, false);
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 1;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920, 1080);
            canvasGo.AddComponent<GraphicRaycaster>();

            // ── 面板底板：屏幕右侧中部 ──
            var panelGo = new GameObject("LlmAlertPanel");
            panelGo.transform.SetParent(canvasGo.transform, false);
            var panelRt = panelGo.AddComponent<RectTransform>();
            panelRt.anchorMin = panelRt.anchorMax = new Vector2(1f, 0.5f);
            panelRt.pivot = new Vector2(1f, 0.5f);
            panelRt.anchoredPosition = new Vector2(-16, 0);
            panelRt.sizeDelta = new Vector2(400, 330);
            var panelImg = panelGo.AddComponent<Image>();
            panelImg.color = ColorPanel;
            panelImg.raycastTarget = true;

            // ── 标题 ──
            _titleText = CreateText(panelGo.transform, new Vector2(0, 0), 400, 32,
                "AI 云脑诊断", 18, TextAnchor.MiddleCenter);
            _titleText.color = ColorHeader;
            _titleText.fontStyle = FontStyle.Bold;

            // ── 服务状态行 ──
            _statusText = CreateText(panelGo.transform, new Vector2(8, 38), 384, 20,
                "○ 等待连接可视化服务…", 12, TextAnchor.UpperLeft);
            _statusText.color = ColorDisconnected;

            // ── 事件大字区 ──
            _eventText = CreateText(panelGo.transform, new Vector2(14, 64), 372, 34,
                "云脑诊断等待中…", 22, TextAnchor.UpperLeft);
            _eventText.color = ColorMeta;
            _eventText.fontStyle = FontStyle.Bold;

            // ── 元信息（置信度/耗时/仿真时刻） ──
            _metaText = CreateText(panelGo.transform, new Vector2(16, 104), 370, 20,
                "", 12, TextAnchor.UpperLeft);
            _metaText.color = ColorMeta;

            // ── 建议区（带分隔底色） ──
            var advicePanelGo = CreatePanel(panelGo.transform, new Vector2(10, 128), 380, 108);
            _adviceText = CreateText(advicePanelGo.transform, new Vector2(8, -8), 364, 92,
                "运行平稳时，云脑将每 60 秒自动诊断一次全网最异常路口。",
                13, TextAnchor.UpperLeft);
            _adviceText.color = new Color(0.92f, 0.94f, 0.97f);

            // ── 诊断按钮行 ──
            _diagnoseBtn = CreateButton(panelGo.transform, new Vector2(10, 244), 180, 36,
                "立即诊断", () =>
                {
                    RequestLlmAlert(null);
                    _requestedAt = Time.time;
                    SetButtonsBusy(true);
                });
            _j25Btn = CreateButton(panelGo.transform, new Vector2(200, 244), 190, 36,
                "诊断 J25（施工点）", () =>
                {
                    RequestLlmAlert("J25");
                    _requestedAt = Time.time;
                    SetButtonsBusy(true);
                });

            // ── 最近更新时间 ──
            _updatedText = CreateText(panelGo.transform, new Vector2(8, 288), 380, 18,
                "", 11, TextAnchor.UpperLeft);
            _updatedText.color = new Color(0.55f, 0.58f, 0.62f);

            SetButtonsBusy(false);
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
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Truncate;
            text.raycastTarget = false;
            return text;
        }

        Button CreateButton(Transform parent, Vector2 pos, float w, float h, string label, UnityEngine.Events.UnityAction onClick)
        {
            var go = new GameObject("Btn_" + label);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = new Vector2(0, 1); // 左上角
            rt.pivot = new Vector2(0, 1);
            rt.anchoredPosition = pos;
            rt.sizeDelta = new Vector2(w, h);

            var img = go.AddComponent<Image>();
            img.color = ColorBtnNormal;

            var btn = go.AddComponent<Button>();
            btn.targetGraphic = img;
            btn.onClick.AddListener(onClick);

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
            text.fontSize = 13;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.raycastTarget = false;

            return btn;
        }

        GameObject CreatePanel(Transform parent, Vector2 pos, float w, float h)
        {
            var go = new GameObject("Panel");
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = new Vector2(0, 1); // 左上角
            rt.pivot = new Vector2(0, 1);
            rt.anchoredPosition = pos;
            rt.sizeDelta = new Vector2(w, h);
            var img = go.AddComponent<Image>();
            img.color = new Color(0.16f, 0.18f, 0.23f, 0.85f);
            img.raycastTarget = false;
            return go;
        }

        void SetButtonsBusy(bool busy)
        {
            if (_diagnoseBtn == null || _j25Btn == null) return;
            var color = busy ? ColorBtnBusy : ColorBtnNormal;
            _diagnoseBtn.GetComponent<Image>().color = color;
            _j25Btn.GetComponent<Image>().color = color;
            _diagnoseBtn.interactable = !busy && _connected;
            _j25Btn.interactable = !busy && _connected;
        }

        // ── 事件处理 ──

        void OnConnectionChanged(bool connected)
        {
            _connected = connected;
            if (_statusText == null) return;

            if (connected)
            {
                _statusText.text = _formalClient != null
                    ? "● 正式后端在线 · 60 秒云脑诊断"
                    : "● 云脑服务在线 · 60 秒自动诊断";
                _statusText.color = ColorConnected;
                SetButtonsBusy(false);
                if (_formalClient == null)
                    Invoke(nameof(RequestAutoDiagnose), 1.5f);
            }
            else
            {
                _statusText.text = "○ 与可视化服务断开 · 自动重连中…";
                _statusText.color = ColorDisconnected;
                SetButtonsBusy(true);
            }
        }

        void OnScenarioSwitched(string scenario, string message)
        {
            _lastAlertWallAt = -1f;
            _updatedText.text = "";
            _eventText.text = "场景切换中，云脑诊断已重置…";
            _eventText.color = ColorMeta;
            _adviceText.text = "等待新场景首次云脑诊断…";
            _metaText.text = "";
        }

        void RequestAutoDiagnose()
        {
            if (_connected && _requestedAt < 0)
            {
                RequestLlmAlert(null);
                _requestedAt = Time.time;
                SetButtonsBusy(true);
                if (_formalClient != null)
                    _nextFormalAutoDiagnoseAt = Time.time + 60f;
            }
        }

        void RequestLlmAlert(string junction)
        {
            if (_formalClient != null)
                _formalClient.RequestLlmAlert(junction);
            else
                _wsClient?.RequestLlmAlert(junction);
        }

        void OnFormalSnapshotReceived(FormalApiSnapshot snapshot)
        {
            // 只有收到同一正式会话的状态后才做首次诊断，避免启动竞态。
            if (_formalClient != null && _connected && _requestedAt < 0 && _nextFormalAutoDiagnoseAt < 0)
            {
                _nextFormalAutoDiagnoseAt = Time.time;
            }
        }

        void OnLlmAlertReceived(LlmAlertData alert)
        {
            _requestedAt = -1f;
            SetButtonsBusy(false);
            _lastAlertWallAt = Time.time;

            var eventCn = string.IsNullOrEmpty(alert.event_cn) ? "正常" : alert.event_cn;
            var eventColor = EventColors.TryGetValue(eventCn, out var c) ? c : ColorMeta;

            if (_eventText != null)
            {
                _eventText.text = $"{alert.junction} · {eventCn}";
                _eventText.color = eventColor;
            }

            var conf = alert.confidence > 0 ? $"{alert.confidence * 100f:F0}%" : "--";
            if (_metaText != null)
            {
                _metaText.text = string.IsNullOrEmpty(alert.advice)
                    ? ""
                    : $"置信度 {conf} · 云脑耗时 {alert.latency_ms / 1000f:F1}s · 仿真 {alert.sim_clock}";
            }

            if (_adviceText != null)
            {
                _adviceText.text = string.IsNullOrEmpty(alert.advice)
                    ? "（云脑未给出建议）"
                    : $"建议：{alert.advice}";
            }

            if (_statusText != null)
            {
                _statusText.text = _formalClient != null
                    ? "● 正式后端在线 · 60 秒云脑诊断"
                    : "● 云脑服务在线 · 60 秒自动诊断";
                _statusText.color = ColorConnected;
            }

            if (_updatedText != null)
            {
                _updatedText.text = $"最近诊断：{DateTime.Now:HH:mm:ss} · 模型 llama.cpp f32";
            }
        }

        void OnLlmAlertError(string message)
        {
            _requestedAt = -1f;
            SetButtonsBusy(false);
            if (_statusText != null)
            {
                // llama-server 未启动等后端诊断失败：显示原因，演示不中断
                _statusText.text = $"○ 云脑离线：{message}";
                _statusText.color = ColorDisconnected;
                _statusText.fontSize = 11;
            }
            if (_updatedText != null)
            {
                _updatedText.text = $"最近尝试：{DateTime.Now:HH:mm:ss}（失败）";
            }
        }

        void OnDestroy()
        {
            if (_wsClient != null)
            {
                _wsClient.OnConnectionChanged -= OnConnectionChanged;
                _wsClient.OnLlmAlertReceived -= OnLlmAlertReceived;
                _wsClient.OnLlmAlertError -= OnLlmAlertError;
                _wsClient.OnScenarioSwitched -= OnScenarioSwitched;
            }
            if (_formalClient != null)
            {
                _formalClient.OnConnectionChanged -= OnConnectionChanged;
                _formalClient.OnLlmAlertReceived -= OnLlmAlertReceived;
                _formalClient.OnLlmAlertError -= OnLlmAlertError;
                _formalClient.OnScenarioSwitched -= OnScenarioSwitched;
                _formalClient.OnSnapshotReceived -= OnFormalSnapshotReceived;
            }
        }
    }
}
