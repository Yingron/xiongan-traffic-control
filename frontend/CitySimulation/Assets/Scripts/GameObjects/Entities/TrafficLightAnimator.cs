using System;
using UnityEngine;

namespace CitySimulation.GameObjects.Entities
{
    /// <summary>
    /// 4相位信号灯动画器，挂载到 TrafficLight GameObject 上。
    ///
    /// 4相位循环：
    ///   Phase 0: 南北直行绿 / 东西红
    ///   Phase 1: 南北保护左转绿 / 东西红
    ///   Phase 2: 东西直行绿 / 南北红
    ///   Phase 3: 东西保护左转绿 / 南北红
    ///   → 回到 Phase 0
    ///
    /// 每个 direction (NS / EW) 各有一组 R/Y/G 灯泡和一组保护左转黄/绿指示灯。
    /// 根据 currentPhase 控制各灯泡的亮灭。
    /// </summary>
    [DisallowMultipleComponent]
    public class TrafficLightAnimator : MonoBehaviour
    {
        // ===================== 相位定义 =====================
        public enum Phase : int
        {
            NS_Green = 0,   // 南北绿灯，东西红灯
            NS_Left = 1,    // 南北保护左转绿灯，东西红灯
            EW_Green = 2,   // 东西绿灯，南北红灯
            EW_Left = 3,    // 东西保护左转绿灯，南北红灯
        }

        // ===================== 配置 =====================
        [Header("相位时长（秒）")]
        [Tooltip("绿灯持续时间")]
        public float greenDuration = 5f;

        [Tooltip("黄灯持续时间")]
        public float yellowDuration = 2f;

        [Header("灯泡外观")]
        [Tooltip("灯泡半径（米）")]
        public float bulbRadius = 0.3f;

        [Tooltip("灯柱高度（米）")]
        public float poleHeight = 4f;

        [Tooltip("灯头间距（米）")]
        public float bulbSpacing = 0.8f;

        [Tooltip("灯组距路口中心偏移（米）")]
        public float armOffset = 3f;

        [Tooltip("保护左转灯列相对直行灯列的水平偏移")]
        public float protectedLeftColumnOffset = 0.85f;

        [Header("运行状态（只读）")]
        [SerializeField] private int _currentPhase = 0;
        [SerializeField] private float _timeInPhase = 0f;

        /// <summary>当前相位 (0-3)</summary>
        public int CurrentPhase
        {
            get => _currentPhase;
            set => SetPhase(value);
        }

        /// <summary>当前相位已持续时间</summary>
        public float TimeInPhase => _timeInPhase;

        // ===================== 内部状态 =====================
        // 4个方向灯组：[0]=North, [1]=South, [2]=East, [3]=West。
        // 每组5个灯泡：[0]=Red, [1]=Yellow, [2]=Green,
        // [3]=ProtectedLeftYellow, [4]=ProtectedLeftGreen。
        private const int BulbCount = 5;
        private const int RedBulb = 0;
        private const int YellowBulb = 1;
        private const int GreenBulb = 2;
        private const int ProtectedLeftYellowBulb = 3;
        private const int ProtectedLeftGreenBulb = 4;
        private GameObject[][] _bulbs;
        private Renderer[][] _bulbRenderers;
        private Material[] _onMaterials;
        private Material[] _offMaterials;
        private bool _initialized;

        // 颜色定义
        private static readonly Color ColorRedOn = new Color(1f, 0.1f, 0.1f);
        private static readonly Color ColorYellowOn = new Color(1f, 0.85f, 0.1f);
        private static readonly Color ColorGreenOn = new Color(0.1f, 1f, 0.2f);
        private static readonly Color ColorOff = new Color(0.15f, 0.15f, 0.15f, 1f);

        // ===================== 生命周期 =====================
        void OnEnable()
        {
            // OnEnable 在组件启用时触发（Edit/Play 模式均有效），
            // 比 Awake 更可靠，因为 OnEnable 在场景完全加载后才执行。
            // 检查是否已有子对象（防止重复创建）
            if (!_initialized || transform.childCount == 0)
            {
                try
                {
                    EnsureInitialized();
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[TrafficLightAnimator] OnEnable init failed: {e.Message}");
                }
            }
        }

        void Awake()
        {
            // 兜底：如果 OnEnable 因某种原因未触发
            if (!_initialized && transform.childCount == 0)
            {
                try
                {
                    EnsureInitialized();
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[TrafficLightAnimator] Awake init failed: {e.Message}");
                }
            }
        }

        void Start()
        {
            // 最终兜底
            if (!_initialized || transform.childCount == 0)
            {
                EnsureInitialized();
            }
        }

        void Update()
        {
            if (!_initialized) return;
            // 自动循环模式（不依赖 TrafficService.Tick 时使用）
            float dt = Time.deltaTime;
            Tick(dt);
        }

        // ===================== 手动重建（Inspector 菜单） =====================
        [ContextMenu("Rebuild Traffic Light Children")]
        public void RebuildChildren()
        {
            // 清除旧子对象
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                var child = transform.GetChild(i);
                if (Application.isPlaying)
                    Destroy(child.gameObject);
                else
                    DestroyImmediate(child.gameObject);
            }
            // 释放旧材质
            DisposeMaterials();
            _initialized = false;
            _bulbs = null;
            _bulbRenderers = null;
            EnsureInitialized();
            Debug.Log($"[TrafficLightAnimator] Rebuilt children for {gameObject.name}");
        }

        // ===================== 初始化 =====================
        private void EnsureInitialized()
        {
            if (_initialized) return;

            // ----- 预先创建所有材质（一次性分配，所有灯泡共享） -----
            _onMaterials = new Material[BulbCount];
            _offMaterials = new Material[BulbCount];
            Color[] onColors = { ColorRedOn, ColorYellowOn, ColorGreenOn, ColorYellowOn, ColorGreenOn };
            string[] matNames = { "Traffic_Red", "Traffic_Yellow", "Traffic_Green", "Traffic_LeftYellow", "Traffic_LeftGreen" };
            for (int i = 0; i < BulbCount; i++)
            {
                _onMaterials[i] = CreateTrafficMat(matNames[i] + "_On", onColors[i], true);
                _offMaterials[i] = CreateTrafficMat(matNames[i] + "_Off", ColorOff, false);
            }
            Material poleMat = CreateTrafficMat("Traffic_Pole", new Color(0.2f, 0.2f, 0.2f), false);

            _bulbs = new GameObject[4][];
            _bulbRenderers = new Renderer[4][];
            string[] dirNames = { "N", "S", "E", "W" };

            for (int dir = 0; dir < 4; dir++)
            {
                _bulbs[dir] = new GameObject[BulbCount];
                _bulbRenderers[dir] = new Renderer[BulbCount];
                string[] bulbNames = { "Red", "Yellow", "Green", "LeftArrow_Yellow", "LeftArrow_Green" };

                // 灯组父节点
                var arm = new GameObject($"Arm_{dirNames[dir]}");
                arm.transform.SetParent(transform, false);

                // 灯柱
                var pole = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                pole.name = "Pole";
                pole.transform.SetParent(arm.transform, false);
                pole.transform.localScale = new Vector3(0.15f, poleHeight * 0.5f, 0.15f);
                pole.transform.localPosition = new Vector3(0, poleHeight * 0.5f, 0);
                // 直接赋值共享材质，不修改材质实例
                var poleR = pole.GetComponent<Renderer>();
                if (poleR != null) poleR.sharedMaterial = poleMat;
                // 移除 Collider（避免阻挡射线/点击）
                var poleCol = pole.GetComponent<Collider>();
                if (poleCol != null)
                {
                    if (Application.isPlaying) Destroy(poleCol);
                    else DestroyImmediate(poleCol);
                }

                // 水平臂方向：N/S 沿 Z 轴，E/W 沿 X 轴
                Vector3 armDir = dir < 2 ? new Vector3(0, 0, dir == 0 ? 1 : -1) : new Vector3(dir == 2 ? 1 : -1, 0, 0);
                arm.transform.localPosition = armDir * armOffset;

                // 直行灯列为红上、黄中、绿下；右侧的两盏小灯专门表示保护左转。
                for (int bulb = 0; bulb < BulbCount; bulb++)
                {
                    var sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                    sphere.name = bulbNames[bulb];
                    sphere.transform.SetParent(arm.transform, false);
                    float columnX = bulb >= ProtectedLeftYellowBulb ? protectedLeftColumnOffset : 0f;
                    int row = bulb >= ProtectedLeftYellowBulb ? bulb - ProtectedLeftYellowBulb : bulb;
                    float radiusScale = bulb >= ProtectedLeftYellowBulb ? 0.8f : 1f;
                    sphere.transform.localScale = Vector3.one * bulbRadius * 2f * radiusScale;
                    sphere.transform.localPosition = new Vector3(columnX, poleHeight - row * bulbSpacing, 0);
                    // 初始全灭（用 off 共享材质）
                    var r = sphere.GetComponent<Renderer>();
                    if (r != null) r.sharedMaterial = _offMaterials[bulb];
                    // 移除 Collider
                    var col = sphere.GetComponent<Collider>();
                    if (col != null)
                    {
                        if (Application.isPlaying) Destroy(col);
                        else DestroyImmediate(col);
                    }
                    _bulbs[dir][bulb] = sphere;
                    _bulbRenderers[dir][bulb] = r;
                }
            }

            _initialized = true;
            ApplyPhaseVisual();
        }

        /// <summary>创建一个带颜色+可选发光的材质（Standard Shader）</summary>
        private static Material CreateTrafficMat(string name, Color color, bool emission)
        {
            var shader = Shader.Find("Standard");
            var mat = shader != null ? new Material(shader) : new Material(Shader.Find("Standard (Specular setup)") ?? Shader.Find("Diffuse"));
            mat.name = name;
            mat.color = color;
            if (emission && mat.HasProperty("_EmissionColor"))
            {
                mat.EnableKeyword("_EMISSION");
                mat.SetColor("_EmissionColor", color * 0.6f);
            }
            return mat;
        }

        // ===================== Tick（可由外部调用或自动 Update）=====================
        /// <summary>
        /// 推进信号灯时间，自动切换相位。
        /// 可由 TrafficService.Tick 调用，也可由 Update 自动推进。
        /// </summary>
        public void Tick(float dt)
        {
            if (dt <= 0f) return;

            _timeInPhase += dt;
            float duration = GetPhaseDuration(_currentPhase);

            if (_timeInPhase >= duration)
            {
                _timeInPhase = 0f;
                _currentPhase = (_currentPhase + 1) % 4;
                ApplyPhaseVisual();
            }
        }

        /// <summary>手动设置相位，重置计时</summary>
        public void SetPhase(int phase)
        {
            _currentPhase = ((phase % 4) + 4) % 4;
            _timeInPhase = 0f;
            ApplyPhaseVisual();
        }

        /// <summary>获取当前相位时长</summary>
        public float GetPhaseDuration(int phase)
        {
            // 四个 SUMO rl4 相位均为有效放行相位；黄灯仅保留为灯头，
            // 不再把保护左转相位误显示成黄灯。
            return greenDuration;
        }

        // ===================== 视觉更新 =====================
        private void ApplyPhaseVisual()
        {
            if (!_initialized) return;

            // dir: 0=N, 1=S (南北方向)；2=E, 3=W (东西方向)
            bool nsStraightGreen = _currentPhase == (int)Phase.NS_Green;
            bool nsLeftGreen = _currentPhase == (int)Phase.NS_Left;
            bool ewStraightGreen = _currentPhase == (int)Phase.EW_Green;
            bool ewLeftGreen = _currentPhase == (int)Phase.EW_Left;

            for (int dir = 0; dir < 4; dir++)
            {
                bool isNS = dir < 2;
                bool straightGreen = isNS ? nsStraightGreen : ewStraightGreen;
                bool leftGreen = isNS ? nsLeftGreen : ewLeftGreen;
                bool red = !straightGreen && !leftGreen;

                SetBulb(dir, RedBulb, red);
                SetBulb(dir, YellowBulb, false);
                SetBulb(dir, GreenBulb, straightGreen);
                SetBulb(dir, ProtectedLeftYellowBulb, false);
                SetBulb(dir, ProtectedLeftGreenBulb, leftGreen);
            }
        }

        private void SetBulb(int dir, int bulbIndex, bool on)
        {
            var r = _bulbRenderers?[dir]?[bulbIndex];
            if (r == null) return;

            // 直接赋值预创建的共享材质（On / Off），
            // 完全避免修改 .material（不会实例化/泄漏）
            var mat = on ? _onMaterials[bulbIndex] : _offMaterials[bulbIndex];
            if (r.sharedMaterial != mat)
                r.sharedMaterial = mat;
        }

        // ===================== 资源清理 =====================
        void OnDestroy()
        {
            DisposeMaterials();
        }

        private void DisposeMaterials()
        {
            if (_onMaterials != null)
            {
                foreach (var m in _onMaterials)
                    if (m != null)
                    {
                        if (Application.isPlaying) Destroy(m);
                        else DestroyImmediate(m);
                    }
                _onMaterials = null;
            }
            if (_offMaterials != null)
            {
                foreach (var m in _offMaterials)
                    if (m != null)
                    {
                        if (Application.isPlaying) Destroy(m);
                        else DestroyImmediate(m);
                    }
                _offMaterials = null;
            }
        }

        // ===================== Gizmos（Editor 可见）=====================
#if UNITY_EDITOR
        void OnDrawGizmos()
        {
            if (_bulbs == null) return;

            for (int dir = 0; dir < 4; dir++)
            {
                if (_bulbs[dir] == null) continue;
                for (int bulb = 0; bulb < BulbCount; bulb++)
                {
                    var b = _bulbs[dir][bulb];
                    if (b == null) continue;

                    Color gizmoColor;
                    switch (bulb)
                    {
                        case 0: gizmoColor = Color.red; break;
                        case 1: gizmoColor = Color.yellow; break;
                        case 2:
                        case ProtectedLeftGreenBulb:
                            gizmoColor = Color.green;
                            break;
                        case ProtectedLeftYellowBulb:
                            gizmoColor = Color.yellow;
                            break;
                        default: gizmoColor = Color.gray; break;
                    }
                    // 实际亮灭时用亮色，不亮时用暗色
                    var rend = b.GetComponent<Renderer>();
                    if (rend != null && rend.sharedMaterial != null)
                    {
                        var matColor = rend.sharedMaterial.color;
                        if (matColor == ColorOff) gizmoColor *= 0.2f;
                    }
                    Gizmos.color = gizmoColor;
                    Gizmos.DrawWireSphere(b.transform.position, bulbRadius);
                }
            }
        }
#endif
    }
}
