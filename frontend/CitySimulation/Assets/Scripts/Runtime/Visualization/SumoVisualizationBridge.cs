using System.Collections.Generic;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using UnityEngine;

namespace CitySimulation.Runtime.Visualization
{
    /// <summary>
    /// 可视化桥接器 — 接收 SUMO 仿真状态，在 Unity 中渲染车辆和信号灯。
    ///
    /// 坐标映射:
    ///   SUMO (x=East, y=North) → Unity (x=East, y=0, z=North)
    ///   SUMO angle (0=North, 90=East) → Unity rotation Y (0=North, 90=East)
    /// </summary>
    [DisallowMultipleComponent]
    public class SumoVisualizationBridge : MonoBehaviour
    {
        [Header("引用")]
        [Tooltip("WebSocket 客户端")]
        public SumoWebSocketClient wsClient;

        [Header("车辆渲染")]
        [Tooltip("普通车辆 Prefab")]
        public GameObject vehiclePrefab;
        [Tooltip("公交车 Prefab (可选)")]
        public GameObject busPrefab;
        [Tooltip("车辆池初始大小")]
        public int poolSize = 80;
        [Tooltip("车辆缩放")]
        public float vehicleScale = 1f;
        [Tooltip("车辆 Y 偏移（高度）。0.35 可防止车辆与路面 z-fighting 闪烁。")]
        public float vehicleYOffset = 0.35f;

        [Header("坐标变换")]
        [Tooltip("SUMO 坐标到 Unity 坐标的缩放系数")]
        public float coordinateScale = 1f;
        [Tooltip("坐标 X 偏移")]
        public float offsetX = 0f;
        [Tooltip("坐标 Z 偏移")]
        public float offsetZ = 0f;

        [Header("信号灯")]
        [Tooltip("是否自动更新信号灯相位")]
        public bool updateTrafficLights = true;

        // ── 车辆对象池 ──
        readonly List<GameObject> _vehiclePool = new();
        readonly Dictionary<string, GameObject> _activeVehicles = new();
        int _poolIndex;

        // ── 当前指标 ──
        public SimMetrics CurrentMetrics { get; private set; }
        public int ActiveVehicleCount => _activeVehicles.Count;

        // ── 信号灯查找 ──
        Dictionary<string, TrafficLightAnimator> _tlAnimators;
        Dictionary<string, int> _lastPhases = new();

        void Start()
        {
            InitializePool();

            if (wsClient != null)
            {
                wsClient.OnStateMessage += OnStateReceived;
            }
            else
            {
                // 尝试自动查找
                wsClient = FindObjectOfType<SumoWebSocketClient>();
                if (wsClient != null)
                {
                    wsClient.OnStateMessage += OnStateReceived;
                }
            }
        }

        void InitializePool()
        {
            if (vehiclePrefab == null)
            {
                // 使用 Resources 中的默认 Prefab
                vehiclePrefab = Resources.Load<GameObject>("Vehicle/Truck_color03");
            }

            var poolParent = new GameObject("VehiclePool");
            poolParent.transform.SetParent(transform, false);

            for (int i = 0; i < poolSize; i++)
            {
                var go = CreateVehicle();
                go.transform.SetParent(poolParent.transform, false);
                go.SetActive(false);
                _vehiclePool.Add(go);
            }
        }

        GameObject CreateVehicle()
        {
            GameObject go;
            if (vehiclePrefab != null)
            {
                go = Instantiate(vehiclePrefab);
            }
            else
            {
                // 回退：创建 Cube
                go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                go.transform.localScale = new Vector3(2f, 1f, 4f);
                var r = go.GetComponent<Renderer>();
                if (r != null)
                {
                    r.material.color = new Color(0.2f, 0.5f, 1f);
                }
            }
            go.transform.localScale *= vehicleScale;

            // 移除 Collider（避免物理干扰）
            var col = go.GetComponent<Collider>();
            if (col != null) Destroy(col);

            return go;
        }

        void OnStateReceived(string raw)
        {
            var state = JsonUtility.FromJson<SimState>(raw);
            if (state == null) return;

            UpdateVehicles(state);
            UpdateTrafficLights(state);
            CurrentMetrics = state.metrics;
        }

        // ── 车辆更新 ──

        void UpdateVehicles(SimState state)
        {
            if (state.vehicles == null) return;

            // 标记当前活跃的车辆 ID
            var currentIds = new HashSet<string>();

            foreach (var veh in state.vehicles)
            {
                if (string.IsNullOrEmpty(veh.id)) continue;
                currentIds.Add(veh.id);

                GameObject go;
                if (!_activeVehicles.TryGetValue(veh.id, out go))
                {
                    // 从池中获取
                    go = GetFromPool();
                    if (go == null) continue;
                    go.name = $"V_{veh.id}";
                    go.SetActive(true);
                    _activeVehicles[veh.id] = go;
                }

                // 更新位置和朝向
                // SUMO: x=East, y=North → Unity: x=East, z=North
                var pos = new Vector3(
                    veh.x * coordinateScale + offsetX,
                    vehicleYOffset,
                    veh.y * coordinateScale + offsetZ
                );
                go.transform.position = pos;

                // SUMO angle: 0=North, 90=East → Unity Y rotation 一致
                go.transform.rotation = Quaternion.Euler(0f, veh.angle, 0f);

                // 根据车辆类型切换颜色/ prefab
                if (!string.IsNullOrEmpty(veh.type))
                {
                    if (veh.type == "bus" && busPrefab != null)
                    {
                        // 可以在这里切换 mesh，但为简化，仅改颜色
                    }
                }
            }

            // 回收不在当前状态中的车辆
            var toRemove = new List<string>();
            foreach (var kvp in _activeVehicles)
            {
                if (!currentIds.Contains(kvp.Key))
                {
                    kvp.Value.SetActive(false);
                    toRemove.Add(kvp.Key);
                }
            }
            foreach (var id in toRemove)
            {
                _activeVehicles.Remove(id);
            }
        }

        GameObject GetFromPool()
        {
            // 尝试从池中找到未激活的对象
            for (int i = 0; i < _vehiclePool.Count; i++)
            {
                _poolIndex = (_poolIndex + 1) % _vehiclePool.Count;
                var go = _vehiclePool[_poolIndex];
                if (!go.activeSelf)
                {
                    return go;
                }
            }

            // 池已耗尽，动态扩展
            var newGo = CreateVehicle();
            newGo.transform.SetParent(_vehiclePool[0].transform.parent, false);
            _vehiclePool.Add(newGo);
            return newGo;
        }

        // ── 信号灯更新 ──

        void UpdateTrafficLights(SimState state)
        {
            if (!updateTrafficLights || state.traffic_lights == null) return;

            if (_tlAnimators == null)
            {
                BuildTrafficLightLookup();
            }

            if (_tlAnimators == null) return;

            foreach (var tl in state.traffic_lights)
            {
                if (string.IsNullOrEmpty(tl.id)) continue;
                if (_tlAnimators.TryGetValue(tl.id, out var animator))
                {
                    // SUMO 与 Unity 均采用 0--3 的四相位约定。必须保留左转
                    // 相位（1/3），否则 DQN 的动作虽已回传到 SUMO，Unity 视觉上
                    // 却会把左转绿灯误显示为直行绿灯，无法完成闭环验收。
                    int unityPhase = ((tl.phase % 4) + 4) % 4;

                    // 仅在相位变化时更新（避免每帧重置计时器）
                    if (!_lastPhases.TryGetValue(tl.id, out int lastPhase) || lastPhase != unityPhase)
                    {
                        animator.SetPhase(unityPhase);
                        _lastPhases[tl.id] = unityPhase;
                    }
                }
            }
        }

        void BuildTrafficLightLookup()
        {
            _tlAnimators = new Dictionary<string, TrafficLightAnimator>();

            // 查找场景中所有 TrafficLightAnimator
            var animators = FindObjectsOfType<TrafficLightAnimator>();
            foreach (var anim in animators)
            {
                // 信号灯 GameObject 的名称应包含路口 ID（如 J01）
                var name = anim.gameObject.name;
                foreach (var tlId in GetExpectedIntersectionIds())
                {
                    if (name.Contains(tlId))
                    {
                        _tlAnimators[tlId] = anim;
                        break;
                    }
                }
            }

            // 如果按名称未找到，尝试按位置匹配
            if (_tlAnimators.Count == 0)
            {
                MatchTrafficLightsByPosition();
            }

            Debug.Log($"[SumoBridge] 信号灯查找完成: 找到 {_tlAnimators.Count}/{30} 个");

            // 设置大持续时间，防止 TrafficLightAnimator 自动切换相位
            // （相位由 SUMO 数据驱动）
            foreach (var anim in _tlAnimators.Values)
            {
                anim.greenDuration = 9999f;
                anim.yellowDuration = 9999f;
            }
        }

        void MatchTrafficLightsByPosition()
        {
            // SUMO 路口坐标（与 xiongan_30.nod.xml 一致，SUMO y=North → Unity z）
            var intersectionPositions = new Dictionary<string, Vector2>
            {
                {"J05", new Vector2(0, 1000)},   {"J07", new Vector2(200, 1000)},
                {"J10", new Vector2(400, 1000)}, {"J01", new Vector2(600, 1000)},
                {"J03", new Vector2(800, 1000)}, {"J14", new Vector2(0, 800)},
                {"J04", new Vector2(200, 800)},  {"J06", new Vector2(400, 800)},
                {"J08", new Vector2(600, 800)},  {"J02", new Vector2(800, 800)},
                {"J17", new Vector2(0, 600)},    {"J09", new Vector2(200, 600)},
                {"J11", new Vector2(400, 600)},  {"J12", new Vector2(600, 600)},
                {"J15", new Vector2(800, 600)},  {"J16", new Vector2(0, 400)},
                {"J18", new Vector2(200, 400)},  {"J19", new Vector2(400, 400)},
                {"J20", new Vector2(600, 400)},  {"J21", new Vector2(800, 400)},
                {"J22", new Vector2(0, 200)},    {"J23", new Vector2(200, 200)},
                {"J24", new Vector2(400, 200)},  {"J25", new Vector2(600, 200)},
                {"J28", new Vector2(800, 200)},  {"J13", new Vector2(0, 0)},
                {"J26", new Vector2(200, 0)},    {"J27", new Vector2(400, 0)},
                {"J29", new Vector2(600, 0)},    {"J30", new Vector2(800, 0)},
            };

            var animators = FindObjectsOfType<TrafficLightAnimator>();
            foreach (var anim in animators)
            {
                var pos = anim.transform.position;
                var unityPos = new Vector2(pos.x, pos.z);

                string bestId = null;
                float bestDist = float.MaxValue;

                foreach (var kvp in intersectionPositions)
                {
                    var sumoPos = kvp.Value;
                    var dist = Vector2.Distance(unityPos, sumoPos);
                    if (dist < bestDist && dist < 50f) // 50 单位容差
                    {
                        bestDist = dist;
                        bestId = kvp.Key;
                    }
                }

                if (bestId != null && !_tlAnimators.ContainsKey(bestId))
                {
                    _tlAnimators[bestId] = anim;
                }
            }
        }

        static string[] GetExpectedIntersectionIds()
        {
            var ids = new string[30];
            for (int i = 0; i < 30; i++)
            {
                ids[i] = $"J{i + 1:D2}";
            }
            return ids;
        }

        /// <summary>
        /// 切换后端场景时清除旧快照，避免车辆、指标或相位短暂残留在新场景中。
        /// </summary>
        public void ResetForScenarioSwitch()
        {
            foreach (var vehicle in _activeVehicles.Values)
            {
                if (vehicle != null)
                {
                    vehicle.SetActive(false);
                }
            }
            _activeVehicles.Clear();
            _lastPhases.Clear();
            CurrentMetrics = null;
        }

        void OnDestroy()
        {
            if (wsClient != null)
            {
                wsClient.OnStateMessage -= OnStateReceived;
            }
        }
    }

    // ── JSON 数据结构 ──

    [System.Serializable]
    public class SimState
    {
        public string type;
        public int step;
        public string scenario;
        public string scenario_label;
        public float simulation_time;
        public SimTrafficLight[] traffic_lights;
        public SimVehicle[] vehicles;
        public SimMetrics metrics;
    }

    [System.Serializable]
    public class SimVehicle
    {
        public string id;
        public float x;
        public float y;
        public float angle;
        public float speed;
        public string type;
    }

    [System.Serializable]
    public class SimTrafficLight
    {
        public string id;
        public int phase;
        public string phase_name;
    }

    [System.Serializable]
    public class SimMetrics
    {
        public int vehicle_count;
        public float avg_queue;
        public float avg_wait;
        public float avg_speed;
        public int total_arrived;
        public int total_departed;
        public float simulation_time;
    }
}
