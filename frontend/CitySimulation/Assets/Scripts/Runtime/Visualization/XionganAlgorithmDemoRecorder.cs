using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using CitySimulation.Runtime.Visualization;
using UnityEngine;
using UnityEngine.UI;
using Debug = UnityEngine.Debug;

#if UNITY_EDITOR
using UnityEditor;
#endif

/// <summary>
/// Records a 175-second, audit-oriented algorithm demo from the real SUMO → ONNX DQN →
/// constraint → SUMO loop.  Every number shown by this component comes from the WebSocket
/// state or a counter derived from distinct server steps in the current recording.
/// </summary>
public sealed class XionganAlgorithmDemoRecorder : MonoBehaviour
{
    const string OutputKey = "Xiongan.AlgorithmDemo.Output";
    const string FfmpegKey = "Xiongan.AlgorithmDemo.Ffmpeg";
    const int Width = 1920;
    const int Height = 1080;
    const int CaptureFps = 10;
    const int DurationSeconds = 175;
    const int TargetFrames = CaptureFps * DurationSeconds;
    const string FocusJunction = "J02";

    readonly List<string> errors = new List<string>();
    readonly List<string> ffmpegTail = new List<string>();
    readonly Dictionary<string, int> lastExecutedActions = new Dictionary<string, int>();
    readonly HashSet<int> distinctJ02Suggestions = new HashSet<int>();

    SumoVisualizationBridge bridge;
    Camera gameCamera;
    Canvas overlayCanvas;
    Text headerText;
    Text segmentText;
    Text decisionTitle;
    Text decisionBody;
    Text decisionStatus;
    Text decisionStats;
    Text evidenceText;
    Image statusBackground;
    Image evidenceBackground;
    string outputPath;
    string ffmpegPath;
    Process encoder;
    DateTime startedAt;
    float realElapsed;
    int framesWritten;
    int ffmpegExitCode = -999;
    int observedServerSteps;
    int observedDecisions;
    int constraintInterventions;
    int appliedActionChanges;
    int j02SuggestionChanges;
    int lastJ02Suggestion = -1;
    string lastStepKey = "";
    bool qValuesObserved;
    bool actionMaskObserved;
    bool constraintObserved;
    bool queueInputsObserved;
    bool modelObserved;
    bool scenarioSwitchRequested;
    bool scenarioSwitchConfirmed;
    string initialScenario = "";
    string finalScenario = "";
    string observedModelId = "";
    float maxObservedBatchLatencyMs;

#if UNITY_EDITOR
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void StartRequestedRecording()
    {
        var output = EditorPrefs.GetString(OutputKey, "");
        var ffmpeg = EditorPrefs.GetString(FfmpegKey, "");
        if (string.IsNullOrWhiteSpace(output) || string.IsNullOrWhiteSpace(ffmpeg)) return;
        EditorPrefs.DeleteKey(OutputKey);
        EditorPrefs.DeleteKey(FfmpegKey);
        var host = new GameObject("Xiongan Algorithm Demo Recorder");
        DontDestroyOnLoad(host);
        var recorder = host.AddComponent<XionganAlgorithmDemoRecorder>();
        recorder.outputPath = output;
        recorder.ffmpegPath = ffmpeg;
    }
#endif

    void Awake()
    {
        Application.logMessageReceived += OnLogMessage;
    }

    IEnumerator Start()
    {
        startedAt = DateTime.Now;
        Directory.CreateDirectory(Path.GetDirectoryName(outputPath));
        EnsureVisualizationBootstrap();
        yield return WaitForBridge(60f);
        if (bridge == null || bridge.wsClient == null || !bridge.wsClient.IsConnected ||
            bridge.ActiveVehicleCount == 0 || bridge.CurrentControlStates == null)
        {
            errors.Add("真实SUMO/ONNX/WebSocket控制链路未在60秒内就绪。");
            WriteReport();
            StopPlayMode();
            yield break;
        }

        gameCamera = Camera.main != null ? Camera.main : FindObjectOfType<Camera>();
        if (gameCamera == null)
        {
            errors.Add("未找到可用Game摄像机。");
            WriteReport();
            StopPlayMode();
            yield break;
        }

        initialScenario = bridge.LastScenario;
        BuildOverlay();

        var originalPosition = gameCamera.transform.position;
        var originalRotation = gameCamera.transform.rotation;
        var originalOrthographic = gameCamera.orthographic;
        var originalOrthographicSize = gameCamera.orthographicSize;
        var originalFieldOfView = gameCamera.fieldOfView;
        var originalNear = gameCamera.nearClipPlane;
        var originalFar = gameCamera.farClipPlane;

        if (!StartEncoder())
        {
            WriteReport();
            StopPlayMode();
            yield break;
        }

        var target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32);
        var texture = new Texture2D(Width, Height, TextureFormat.RGBA32, false);
        var oldTarget = gameCamera.targetTexture;
        var oldActive = RenderTexture.active;
        var recordingStarted = Time.realtimeSinceStartup;
        var closeupApplied = false;
        var overviewRestored = false;

        try
        {
            while (framesWritten < TargetFrames)
            {
                realElapsed = Time.realtimeSinceStartup - recordingStarted;
                UpdateOverlay();

                if (!closeupApplied && realElapsed >= 15f)
                {
                    SetJ02Closeup();
                    closeupApplied = true;
                }

                if (!scenarioSwitchRequested && realElapsed >= 145f)
                {
                    scenarioSwitchRequested = true;
                    Action<string, string> handler = null;
                    handler = (scenario, message) =>
                    {
                        if (scenario != "real_offpeak") return;
                        scenarioSwitchConfirmed = true;
                        bridge.wsClient.OnScenarioSwitched -= handler;
                    };
                    bridge.wsClient.OnScenarioSwitched += handler;
                    bridge.wsClient.SwitchScenario("real_offpeak");
                }

                if (!overviewRestored && realElapsed >= 160f)
                {
                    RestoreCamera(originalPosition, originalRotation, originalOrthographic,
                        originalOrthographicSize, originalFieldOfView, originalNear, originalFar);
                    overviewRestored = true;
                }

                var desiredFrames = Mathf.Clamp(Mathf.FloorToInt(realElapsed * CaptureFps) + 1, 1, TargetFrames);
                if (desiredFrames > framesWritten)
                {
                    gameCamera.targetTexture = target;
                    RenderTexture.active = target;
                    gameCamera.Render();
                    texture.ReadPixels(new Rect(0, 0, Width, Height), 0, 0, false);
                    texture.Apply(false, false);
                    var raw = texture.GetRawTextureData<byte>().ToArray();
                    while (framesWritten < desiredFrames)
                    {
                        encoder.StandardInput.BaseStream.Write(raw, 0, raw.Length);
                        framesWritten++;
                    }
                }
                yield return null;
            }
        }
        finally
        {
            gameCamera.targetTexture = oldTarget;
            RenderTexture.active = oldActive;
            RestoreCamera(originalPosition, originalRotation, originalOrthographic,
                originalOrthographicSize, originalFieldOfView, originalNear, originalFar);
            if (overlayCanvas != null) Destroy(overlayCanvas.gameObject);
            Destroy(target);
            Destroy(texture);
            FinishEncoder();
        }

        finalScenario = bridge != null ? bridge.LastScenario : "";
        realElapsed = Time.realtimeSinceStartup - recordingStarted;
        WriteReport();
        StopPlayMode();
    }

    void EnsureVisualizationBootstrap()
    {
        bridge = FindObjectOfType<SumoVisualizationBridge>();
        if (bridge != null) return;
        var host = new GameObject("SUMO Visualization Runtime");
        DontDestroyOnLoad(host);
        host.AddComponent<VisualizationBootstrap>();
        bridge = host.GetComponent<SumoVisualizationBridge>();
    }

    IEnumerator WaitForBridge(float timeout)
    {
        var begin = Time.realtimeSinceStartup;
        while (Time.realtimeSinceStartup - begin < timeout)
        {
            if (bridge == null) bridge = FindObjectOfType<SumoVisualizationBridge>();
            if (bridge != null && bridge.wsClient != null && bridge.wsClient.IsConnected &&
                bridge.ReceivedStateCount >= 2 && bridge.ActiveVehicleCount > 0 &&
                bridge.CurrentControlStates != null && bridge.CurrentControlStates.Length == 30)
                yield break;
            yield return null;
        }
    }

    void BuildOverlay()
    {
        var canvasObject = new GameObject("Algorithm Demo Canvas");
        DontDestroyOnLoad(canvasObject);
        overlayCanvas = canvasObject.AddComponent<Canvas>();
        overlayCanvas.renderMode = RenderMode.ScreenSpaceCamera;
        overlayCanvas.worldCamera = gameCamera;
        overlayCanvas.planeDistance = 1f;
        overlayCanvas.sortingOrder = 1200;
        var scaler = canvasObject.AddComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920f, 1080f);

        var header = CreatePanel(canvasObject.transform, "Header", new Vector2(0f, 1f), new Vector2(0f, 1f),
            new Vector2(0f, 0f), new Vector2(1920f, 98f), new Color(0.015f, 0.045f, 0.09f, 0.94f));
        headerText = CreateText(header.transform, new Vector2(36f, -18f), new Vector2(1120f, 55f), 34, FontStyle.Bold);
        headerText.text = "算法闭环实录｜30路口 ONNX DQN 协同控制";
        headerText.color = new Color(0.38f, 0.88f, 1f);
        var badge = CreateText(header.transform, new Vector2(1230f, -24f), new Vector2(650f, 48f), 24, FontStyle.Bold);
        badge.alignment = TextAnchor.UpperRight;
        badge.text = "真实SUMO状态  ·  每5秒决策  ·  服务端约束";
        badge.color = new Color(0.88f, 0.95f, 1f);

        segmentText = CreateText(canvasObject.transform, new Vector2(38f, -120f), new Vector2(1080f, 52f), 30, FontStyle.Bold);
        segmentText.color = Color.white;

        var panel = CreatePanel(canvasObject.transform, "Decision Audit Panel", new Vector2(1f, 0.5f), new Vector2(1f, 0.5f),
            new Vector2(-28f, -8f), new Vector2(720f, 820f), new Color(0.02f, 0.07f, 0.13f, 0.93f));
        decisionTitle = CreateText(panel.transform, new Vector2(26f, -22f), new Vector2(668f, 52f), 31, FontStyle.Bold);
        decisionTitle.color = new Color(0.32f, 0.85f, 1f);
        decisionBody = CreateText(panel.transform, new Vector2(26f, -88f), new Vector2(668f, 510f), 25, FontStyle.Normal);
        decisionBody.lineSpacing = 1.10f;

        var statusPanel = CreatePanel(panel.transform, "Decision Status", new Vector2(0f, 1f), new Vector2(0f, 1f),
            new Vector2(24f, -612f), new Vector2(672f, 96f), new Color(0.03f, 0.36f, 0.25f, 0.92f));
        statusBackground = statusPanel.GetComponent<Image>();
        decisionStatus = CreateText(statusPanel.transform, new Vector2(18f, -12f), new Vector2(636f, 72f), 24, FontStyle.Bold);
        decisionStatus.lineSpacing = 0.95f;

        decisionStats = CreateText(panel.transform, new Vector2(28f, -720f), new Vector2(660f, 70f), 22, FontStyle.Normal);
        decisionStats.color = new Color(0.80f, 0.88f, 0.96f);

        var evidencePanel = CreatePanel(canvasObject.transform, "Evidence Note", new Vector2(0f, 0f), new Vector2(0f, 0f),
            new Vector2(32f, 24f), new Vector2(1125f, 132f), new Color(0.02f, 0.07f, 0.13f, 0.92f));
        evidenceBackground = evidencePanel.GetComponent<Image>();
        evidenceText = CreateText(evidencePanel.transform, new Vector2(24f, -18f), new Vector2(1075f, 98f), 24, FontStyle.Bold);
        evidenceText.lineSpacing = 1.10f;
    }

    static GameObject CreatePanel(Transform parent, string name, Vector2 anchor, Vector2 pivot,
        Vector2 position, Vector2 size, Color color)
    {
        var panel = new GameObject(name);
        panel.transform.SetParent(parent, false);
        var rect = panel.AddComponent<RectTransform>();
        rect.anchorMin = rect.anchorMax = anchor;
        rect.pivot = pivot;
        rect.anchoredPosition = position;
        rect.sizeDelta = size;
        var image = panel.AddComponent<Image>();
        image.color = color;
        image.raycastTarget = false;
        return panel;
    }

    static Text CreateText(Transform parent, Vector2 position, Vector2 size, int fontSize, FontStyle style)
    {
        var textObject = new GameObject("Text");
        textObject.transform.SetParent(parent, false);
        var rect = textObject.AddComponent<RectTransform>();
        rect.anchorMin = rect.anchorMax = new Vector2(0f, 1f);
        rect.pivot = new Vector2(0f, 1f);
        rect.anchoredPosition = position;
        rect.sizeDelta = size;
        var text = textObject.AddComponent<Text>();
        text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        text.fontSize = fontSize;
        text.fontStyle = style;
        text.alignment = TextAnchor.UpperLeft;
        text.color = new Color(0.94f, 0.97f, 1f);
        text.raycastTarget = false;
        return text;
    }

    void UpdateOverlay()
    {
        UpdateCountersForNewStep();
        UpdateSegmentText();

        var control = bridge != null ? bridge.GetControlState(FocusJunction) : null;
        var metrics = bridge != null ? bridge.CurrentMetrics : null;
        var scenario = bridge != null ? ScenarioLabel(bridge.LastScenario) : "未连接";
        if (control == null || metrics == null)
        {
            decisionTitle.text = FocusJunction + " · 等待新的控制快照";
            decisionBody.text = "场景：" + scenario + "\n\n正在等待SUMO状态、ONNX输出和服务端执行结果……";
            decisionStatus.text = "场景切换中 · 等待首个有效快照";
            statusBackground.color = new Color(0.34f, 0.25f, 0.04f, 0.95f);
            UpdateEvidenceText();
            return;
        }

        decisionTitle.text = FocusJunction + " · DQN实时决策审计";
        var model = ShortModelId(bridge.CurrentModelId);
        var queue = FormatQueues(control.queue_nsew);
        var mask = FormatMask(control.action_mask);
        var qValues = FormatQValues(control.q_values, control.action_mask);
        decisionBody.text =
            "场景：" + scenario + "    仿真时间：" + metrics.simulation_time.ToString("F0") + " s\n" +
            "模型：" + model + "\n" +
            "后端：ONNX CPU    30路口批量推理：" + bridge.LastInferenceLatencyMs.ToString("F3") + " ms\n\n" +
            "输入排队（辆，N / S / E / W，封顶15）\n" + queue + "\n\n" +
            "动作掩码（需求门控）\n" + mask + "\n\n" +
            "掩码后Q值\n" + qValues + "\n\n" +
            "DQN建议：A" + control.requested_action +
            "    约束后下发：A" + control.executed_action +
            "    帧末相位：A" + control.current_phase + "\n" +
            "帧末相位已持续：" + control.phase_elapsed.ToString("F0") + " s    路口模板：" + control.template;

        if (control.constrained)
        {
            decisionStatus.text = "最小绿灯约束｜DQN A" + control.requested_action +
                                  " → 下发 A" + control.executed_action + "\n" +
                                  "决策时还需 " + control.min_green_remaining.ToString("F0") +
                                  " 秒｜帧末相位 A" + control.current_phase;
            statusBackground.color = new Color(0.50f, 0.24f, 0.035f, 0.96f);
        }
        else
        {
            decisionStatus.text = "DQN建议已下发｜A" + control.requested_action + " → A" + control.executed_action +
                                  "\n帧末相位 A" + control.current_phase;
            statusBackground.color = new Color(0.03f, 0.36f, 0.25f, 0.96f);
        }

        decisionStats.text =
            "本次录制累计：" + observedServerSteps + "个控制周期 · " + observedDecisions +
            "个路口决策\n约束介入 " + constraintInterventions + " 次 · 下发动作变化 " + appliedActionChanges +
            " 次 · J02建议覆盖 " + distinctJ02Suggestions.Count + " 类动作";
        UpdateEvidenceText();
    }

    void UpdateSegmentText()
    {
        if (realElapsed < 15f) segmentText.text = "01  三十路口并行推理 · 全网实时运行";
        else if (realElapsed < 40f) segmentText.text = "02  J02输入状态 · 四向排队实时进入模型";
        else if (realElapsed < 75f) segmentText.text = "03  需求门控与Q值 · 形成DQN建议动作";
        else if (realElapsed < 110f) segmentText.text = "04  建议动作 → 最小绿灯约束 → 下发执行";
        else if (realElapsed < 145f) segmentText.text = "05  当前会话决策统计 + 归档对比结果";
        else if (realElapsed < 160f) segmentText.text = "06  早高峰 → 平峰 · 模型与状态重新加载";
        else segmentText.text = "07  平峰模型在线 · 三十路口恢复运行";
    }

    void UpdateEvidenceText()
    {
        if (realElapsed < 110f)
        {
            evidenceText.text =
                "实时闭环：22维局部状态 + 4维需求掩码 → ONNX DQN → 最小绿灯约束 → SUMO执行\n" +
                "面板数据来自当前WebSocket控制快照；动作编号按路口模板解释。";
            evidenceBackground.color = new Color(0.02f, 0.07f, 0.13f, 0.92f);
        }
        else if (realElapsed < 145f)
        {
            evidenceText.text =
                "归档对比（30路口，3回合×720步，种子42—44）：奖励 +11.0% / −1.6% / +9.9%\n" +
                "等待 +3.4% / +2533.5% / +14.1%；碰撞 DQN/定周期：14/0、8/0、7/0｜非当前帧实时结果";
            evidenceBackground.color = new Color(0.30f, 0.16f, 0.025f, 0.94f);
        }
        else
        {
            evidenceText.text =
                "场景切换保留同一数据契约：状态 → 动作掩码 → 场景专用ONNX模型 → 约束执行\n" +
                "实时演示证明控制链路；算法优劣以归档对比结果为准。";
            evidenceBackground.color = new Color(0.02f, 0.18f, 0.23f, 0.94f);
        }
    }

    void UpdateCountersForNewStep()
    {
        if (bridge == null || bridge.CurrentControlStates == null || bridge.CurrentControlStates.Length == 0) return;
        var stepKey = bridge.LastScenario + ":" + bridge.LastServerStep;
        if (stepKey == lastStepKey) return;
        lastStepKey = stepKey;
        observedServerSteps++;
        modelObserved |= !string.IsNullOrEmpty(bridge.CurrentModelId);
        if (!string.IsNullOrEmpty(bridge.CurrentModelId)) observedModelId = bridge.CurrentModelId;
        maxObservedBatchLatencyMs = Mathf.Max(maxObservedBatchLatencyMs, bridge.LastInferenceLatencyMs);

        foreach (var control in bridge.CurrentControlStates)
        {
            if (control == null) continue;
            observedDecisions++;
            constraintInterventions += control.constrained ? 1 : 0;
            constraintObserved |= control.constrained;
            qValuesObserved |= control.q_values != null && control.q_values.Length == 4;
            actionMaskObserved |= control.action_mask != null && control.action_mask.Length == 4;
            queueInputsObserved |= control.queue_nsew != null && control.queue_nsew.Length == 4;

            int lastAction;
            if (lastExecutedActions.TryGetValue(control.id, out lastAction) && lastAction != control.executed_action)
                appliedActionChanges++;
            lastExecutedActions[control.id] = control.executed_action;

            if (control.id == FocusJunction)
            {
                distinctJ02Suggestions.Add(control.requested_action);
                if (lastJ02Suggestion >= 0 && lastJ02Suggestion != control.requested_action) j02SuggestionChanges++;
                lastJ02Suggestion = control.requested_action;
            }
        }
    }

    static string FormatQueues(float[] values)
    {
        if (values == null || values.Length < 4) return "等待输入……";
        return "N " + values[0].ToString("F1") + "    S " + values[1].ToString("F1") +
               "    E " + values[2].ToString("F1") + "    W " + values[3].ToString("F1");
    }

    static string FormatMask(int[] mask)
    {
        if (mask == null || mask.Length < 4) return "等待掩码……";
        return string.Join("    ", Enumerable.Range(0, 4).Select(index =>
            "A" + index + " " + (mask[index] != 0 ? "有效" : "禁用")));
    }

    static string FormatQValues(float[] values, int[] mask)
    {
        if (values == null || values.Length < 4) return "等待Q值……";
        return string.Join("    ", Enumerable.Range(0, 4).Select(index =>
            "A" + index + " " + (mask != null && mask.Length > index && mask[index] == 0
                ? "—"
                : values[index].ToString("F2"))));
    }

    static string ShortModelId(string value)
    {
        if (string.IsNullOrEmpty(value)) return "等待模型信息";
        return value.Replace("edge-real-", "").Replace("-onnx-v1", " · ONNX v1");
    }

    static string ScenarioLabel(string value)
    {
        if (value == "real_peak") return "早高峰";
        if (value == "real_offpeak") return "平峰";
        if (value == "real_evening") return "晚高峰";
        return string.IsNullOrEmpty(value) ? "未记录" : value;
    }

    void SetJ02Closeup()
    {
        var junction = new Vector3(800f, 0f, 800f);
        gameCamera.transform.position = junction + new Vector3(38f, 27f, -46f);
        gameCamera.transform.LookAt(junction + Vector3.up * 1.1f);
        gameCamera.orthographic = false;
        gameCamera.fieldOfView = 35f;
        gameCamera.nearClipPlane = 0.1f;
        gameCamera.farClipPlane = 600f;
    }

    void RestoreCamera(Vector3 position, Quaternion rotation, bool orthographic,
        float orthographicSize, float fieldOfView, float nearClip, float farClip)
    {
        gameCamera.transform.position = position;
        gameCamera.transform.rotation = rotation;
        gameCamera.orthographic = orthographic;
        gameCamera.orthographicSize = orthographicSize;
        gameCamera.fieldOfView = fieldOfView;
        gameCamera.nearClipPlane = nearClip;
        gameCamera.farClipPlane = farClip;
    }

    bool StartEncoder()
    {
        if (!File.Exists(ffmpegPath))
        {
            errors.Add("FFmpeg不存在：" + ffmpegPath);
            return false;
        }
        var args = "-y -f rawvideo -pixel_format rgba -video_size 1920x1080 -framerate 10 " +
                   "-i pipe:0 -vf vflip -an -c:v libx264 -preset ultrafast -crf 17 " +
                   "-pix_fmt yuv420p -movflags +faststart " + Quote(outputPath);
        encoder = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = ffmpegPath,
                Arguments = args,
                UseShellExecute = false,
                RedirectStandardInput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            },
            EnableRaisingEvents = true,
        };
        encoder.ErrorDataReceived += (sender, eventArgs) =>
        {
            if (string.IsNullOrEmpty(eventArgs.Data)) return;
            lock (ffmpegTail)
            {
                ffmpegTail.Add(eventArgs.Data);
                if (ffmpegTail.Count > 60) ffmpegTail.RemoveAt(0);
            }
        };
        encoder.Start();
        encoder.BeginErrorReadLine();
        return true;
    }

    void FinishEncoder()
    {
        if (encoder == null) return;
        try
        {
            encoder.StandardInput.Close();
            if (!encoder.WaitForExit(90000))
            {
                errors.Add("FFmpeg在90秒内未结束。");
                encoder.Kill();
            }
            ffmpegExitCode = encoder.HasExited ? encoder.ExitCode : -998;
            if (ffmpegExitCode != 0) errors.Add("FFmpeg退出码：" + ffmpegExitCode);
        }
        catch (Exception exception)
        {
            errors.Add("结束FFmpeg失败：" + exception.Message);
        }
        finally
        {
            encoder.Dispose();
            encoder = null;
        }
    }

    void WriteReport()
    {
        var report = new RecordingReport
        {
            unityVersion = Application.unityVersion,
            projectPath = Directory.GetParent(Application.dataPath).FullName,
            startedAtLocal = startedAt.ToString("yyyy-MM-dd HH:mm:ss"),
            output = outputPath,
            width = Width,
            height = Height,
            captureFps = CaptureFps,
            targetDurationSeconds = DurationSeconds,
            framesWritten = framesWritten,
            realElapsedSeconds = realElapsed,
            initialScenario = initialScenario,
            finalScenario = finalScenario,
            modelId = observedModelId,
            observedServerSteps = observedServerSteps,
            observedDecisions = observedDecisions,
            constraintInterventions = constraintInterventions,
            appliedActionChanges = appliedActionChanges,
            j02DistinctSuggestedActions = distinctJ02Suggestions.Count,
            j02SuggestionChanges = j02SuggestionChanges,
            qValuesObserved = qValuesObserved,
            actionMaskObserved = actionMaskObserved,
            queueInputsObserved = queueInputsObserved,
            modelObserved = modelObserved,
            constraintObserved = constraintObserved,
            scenarioSwitchRequested = scenarioSwitchRequested,
            scenarioSwitchConfirmed = scenarioSwitchConfirmed,
            maxObservedBatchLatencyMs = maxObservedBatchLatencyMs,
            ffmpegExitCode = ffmpegExitCode,
            errors = errors,
            ffmpegTail = ffmpegTail,
        };
        File.WriteAllText(Path.Combine(Path.GetDirectoryName(outputPath), "algorithm_demo_recording.json"),
            JsonUtility.ToJson(report, true));
    }

    void OnLogMessage(string condition, string stackTrace, LogType type)
    {
        if (type != LogType.Error && type != LogType.Exception && type != LogType.Assert) return;
        if (errors.Count < 50) errors.Add(type + ": " + condition);
    }

    void OnDestroy()
    {
        Application.logMessageReceived -= OnLogMessage;
    }

    static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    static void StopPlayMode()
    {
#if UNITY_EDITOR
        EditorApplication.isPlaying = false;
#endif
    }

    [Serializable]
    sealed class RecordingReport
    {
        public string unityVersion;
        public string projectPath;
        public string startedAtLocal;
        public string output;
        public int width;
        public int height;
        public int captureFps;
        public int targetDurationSeconds;
        public int framesWritten;
        public float realElapsedSeconds;
        public string initialScenario;
        public string finalScenario;
        public string modelId;
        public int observedServerSteps;
        public int observedDecisions;
        public int constraintInterventions;
        public int appliedActionChanges;
        public int j02DistinctSuggestedActions;
        public int j02SuggestionChanges;
        public bool qValuesObserved;
        public bool actionMaskObserved;
        public bool queueInputsObserved;
        public bool modelObserved;
        public bool constraintObserved;
        public bool scenarioSwitchRequested;
        public bool scenarioSwitchConfirmed;
        public float maxObservedBatchLatencyMs;
        public int ffmpegExitCode;
        public List<string> errors;
        public List<string> ffmpegTail;
    }
}
