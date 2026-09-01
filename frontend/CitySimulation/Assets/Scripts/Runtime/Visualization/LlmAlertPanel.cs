using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;

namespace CitySimulation.Runtime.Visualization
{
    /// <summary>
    /// Runtime cloud-brain alert panel. It submits the latest live SUMO context
    /// to the FastAPI LLM endpoint and presents the structured event and advice.
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(SumoVisualizationBridge))]
    public class LlmAlertPanel : MonoBehaviour
    {
        [Header("LLM API")]
        public string apiBaseUrl = "http://127.0.0.1:8000";
        [Min(5)] public int requestTimeoutSeconds = 35;

        SumoVisualizationBridge _bridge;
        Font _font;
        Button _analyzeButton;
        Text _statusText;
        Text _junctionText;
        Text _eventText;
        Text _metaText;
        Text _adviceText;
        bool _requestInFlight;

        static readonly Color PanelColor = new Color(0.035f, 0.075f, 0.13f, 0.94f);
        static readonly Color AccentColor = new Color(0.15f, 0.72f, 1f, 1f);
        static readonly Color SuccessColor = new Color(0.25f, 0.9f, 0.55f, 1f);
        static readonly Color ErrorColor = new Color(1f, 0.38f, 0.3f, 1f);

        void Start()
        {
            _bridge = GetComponent<SumoVisualizationBridge>();
            _font = Resources.Load<Font>("Fonts/simhei");
            if (_font == null)
                _font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            BuildUI();
        }

        void BuildUI()
        {
            var canvasGo = new GameObject("LlmAlertCanvas");
            canvasGo.transform.SetParent(transform, false);
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 20;
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920, 1080);
            canvasGo.AddComponent<GraphicRaycaster>();

            var panel = new GameObject("CloudBrainAlertPanel");
            panel.transform.SetParent(canvasGo.transform, false);
            var panelRt = panel.AddComponent<RectTransform>();
            panelRt.anchorMin = panelRt.anchorMax = new Vector2(1f, 0f);
            panelRt.pivot = new Vector2(1f, 0f);
            panelRt.anchoredPosition = new Vector2(-24f, 24f);
            panelRt.sizeDelta = new Vector2(500f, 330f);
            panel.AddComponent<Image>().color = PanelColor;

            var accent = new GameObject("Accent");
            accent.transform.SetParent(panel.transform, false);
            var accentRt = accent.AddComponent<RectTransform>();
            accentRt.anchorMin = new Vector2(0f, 1f);
            accentRt.anchorMax = new Vector2(1f, 1f);
            accentRt.pivot = new Vector2(0.5f, 1f);
            accentRt.sizeDelta = new Vector2(0f, 5f);
            accent.AddComponent<Image>().color = AccentColor;

            var title = CreateText(panel.transform, "Title", new Vector2(20, -18), 310, 34,
                "城市云脑 · LLM 交通告警", 21, FontStyle.Bold);
            title.color = Color.white;

            _statusText = CreateText(panel.transform, "Status", new Vector2(340, -23), 140, 28,
                "● 等待分析", 14, FontStyle.Bold);
            _statusText.alignment = TextAnchor.UpperRight;
            _statusText.color = AccentColor;

            _junctionText = CreateText(panel.transform, "Junction", new Vector2(20, -65), 180, 28,
                "分析路口：等待实时数据", 15, FontStyle.Normal);
            _junctionText.color = new Color(0.72f, 0.82f, 0.9f);

            _eventText = CreateText(panel.transform, "Event", new Vector2(20, -102), 455, 42,
                "事件：--", 25, FontStyle.Bold);
            _eventText.color = Color.white;

            _metaText = CreateText(panel.transform, "Meta", new Vector2(20, -148), 455, 26,
                "置信度：--    云脑延迟：--", 14, FontStyle.Normal);
            _metaText.color = new Color(0.67f, 0.76f, 0.84f);

            var adviceLabel = CreateText(panel.transform, "AdviceLabel", new Vector2(20, -184), 455, 24,
                "管控建议", 15, FontStyle.Bold);
            adviceLabel.color = AccentColor;

            _adviceText = CreateText(panel.transform, "Advice", new Vector2(20, -211), 455, 70,
                "点击“云脑分析”，识别当前路口事件并生成建议。", 15, FontStyle.Normal);
            _adviceText.horizontalOverflow = HorizontalWrapMode.Wrap;
            _adviceText.verticalOverflow = VerticalWrapMode.Truncate;
            _adviceText.color = new Color(0.92f, 0.95f, 0.98f);

            _analyzeButton = CreateButton(panel.transform, new Vector2(20, -290), 455, 30,
                "云脑分析当前路口", AnalyzeLatestContext);
            _analyzeButton.interactable = false;
        }

        void Update()
        {
            if (_requestInFlight || _bridge == null || _bridge.CurrentLlmContext == null)
                return;
            var junction = _bridge.CurrentLlmContext.junction;
            _junctionText.text = string.IsNullOrEmpty(junction)
                ? "分析路口：等待实时数据"
                : "分析路口：" + junction + "（实时 SUMO 状态）";
            _analyzeButton.interactable = !string.IsNullOrEmpty(_bridge.CurrentLlmContext.text);
        }

        public void AnalyzeLatestContext()
        {
            if (_requestInFlight) return;
            var context = _bridge != null ? _bridge.CurrentLlmContext : null;
            if (context == null || string.IsNullOrEmpty(context.text))
            {
                ShowError("尚未收到实时交通状态，请确认可视化服务已连接。");
                return;
            }
            StartCoroutine(PostAnalysis(context.junction, context.text));
        }

        IEnumerator PostAnalysis(string junction, string contextText)
        {
            _requestInFlight = true;
            _analyzeButton.interactable = false;
            _statusText.text = "● 分析中…";
            _statusText.color = new Color(1f, 0.75f, 0.2f);
            _eventText.text = "事件：云脑正在研判";
            _metaText.text = "正在调用 qwen-traffic…";
            _adviceText.text = "正在综合排队、等待、占有率、车速与当前信号相位。";

            var requestBody = JsonUtility.ToJson(new LlmAnalyzeRequest
            {
                text = contextText,
                junction = junction
            });
            var url = apiBaseUrl.TrimEnd('/') + "/api/v1/llm/analyze";
            using (var request = new UnityWebRequest(url, UnityWebRequest.kHttpVerbPOST))
            {
                request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(requestBody));
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json; charset=utf-8");
                request.timeout = requestTimeoutSeconds;
                yield return request.SendWebRequest();

                if (request.result != UnityWebRequest.Result.Success)
                {
                    var details = string.IsNullOrWhiteSpace(request.downloadHandler.text)
                        ? request.error
                        : request.downloadHandler.text;
                    ShowError("LLM 服务调用失败（HTTP " + request.responseCode + "）\n" + Shorten(details, 100));
                }
                else
                {
                    LlmAnalyzeResponse response = null;
                    try { response = JsonUtility.FromJson<LlmAnalyzeResponse>(request.downloadHandler.text); }
                    catch (System.Exception error) { Debug.LogException(error); }
                    if (response == null || string.IsNullOrEmpty(response.@event))
                        ShowError("LLM 返回内容无法解析，请检查 API 日志。");
                    else
                        ShowResult(response);
                }
            }

            _requestInFlight = false;
            _analyzeButton.interactable = true;
        }

        void ShowResult(LlmAnalyzeResponse response)
        {
            _statusText.text = "● 分析完成";
            _statusText.color = SuccessColor;
            _eventText.text = "事件：" + response.@event;
            _eventText.color = EventColor(response.event_en);
            var confidence = response.confidence >= 0f ? (response.confidence * 100f).ToString("F0") + "%" : "--";
            _metaText.text = "置信度：" + confidence + "    云脑延迟：" + response.latency_ms.ToString("F0") + " ms";
            _adviceText.text = string.IsNullOrEmpty(response.advice) ? "模型未返回管控建议。" : response.advice;
        }

        void ShowError(string message)
        {
            _statusText.text = "● 服务异常";
            _statusText.color = ErrorColor;
            _eventText.text = "事件：分析失败";
            _eventText.color = ErrorColor;
            _metaText.text = "请确认 8000 端口 API 与 8081 端口 LLM 服务均已启动";
            _adviceText.text = message;
        }

        static Color EventColor(string eventName)
        {
            switch (eventName)
            {
                case "normal": return SuccessColor;
                case "congestion": return new Color(1f, 0.72f, 0.2f);
                case "spillover": return new Color(1f, 0.42f, 0.18f);
                case "incident": return ErrorColor;
                default: return Color.white;
            }
        }

        static string Shorten(string value, int length)
        {
            if (string.IsNullOrEmpty(value) || value.Length <= length) return value;
            return value.Substring(0, length) + "…";
        }

        Text CreateText(Transform parent, string name, Vector2 position, float width, float height,
            string content, int size, FontStyle style)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = new Vector2(0f, 1f);
            rt.pivot = new Vector2(0f, 1f);
            rt.anchoredPosition = position;
            rt.sizeDelta = new Vector2(width, height);
            var text = go.AddComponent<Text>();
            text.font = _font;
            text.text = content;
            text.fontSize = size;
            text.fontStyle = style;
            text.alignment = TextAnchor.UpperLeft;
            text.raycastTarget = false;
            return text;
        }

        Button CreateButton(Transform parent, Vector2 position, float width, float height,
            string label, UnityEngine.Events.UnityAction onClick)
        {
            var go = new GameObject("AnalyzeButton");
            go.transform.SetParent(parent, false);
            var rt = go.AddComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = new Vector2(0f, 1f);
            rt.pivot = new Vector2(0f, 1f);
            rt.anchoredPosition = position;
            rt.sizeDelta = new Vector2(width, height);
            var image = go.AddComponent<Image>();
            image.color = new Color(0.08f, 0.45f, 0.68f, 1f);
            var button = go.AddComponent<Button>();
            button.targetGraphic = image;
            button.onClick.AddListener(onClick);
            var labelText = CreateText(go.transform, "Label", Vector2.zero, width, height, label, 15, FontStyle.Bold);
            var labelRt = labelText.rectTransform;
            labelRt.anchorMin = Vector2.zero;
            labelRt.anchorMax = Vector2.one;
            labelRt.pivot = new Vector2(0.5f, 0.5f);
            labelRt.anchoredPosition = Vector2.zero;
            labelRt.sizeDelta = Vector2.zero;
            labelText.alignment = TextAnchor.MiddleCenter;
            return button;
        }
    }

    [System.Serializable]
    public class LlmAnalyzeRequest
    {
        public string text;
        public string junction;
    }

    [System.Serializable]
    public class LlmAnalyzeResponse
    {
        public string junction;
        public string @event;
        public string event_en;
        public float confidence = -1f;
        public string advice;
        public float latency_ms;
        public string llm_backend;
        public string llm_model;
    }
}
