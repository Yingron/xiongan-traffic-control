using System.Collections.Generic;
using CitySimulation.DTO;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using CitySimulation.Runtime.Services;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;
using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    public sealed class SimulationRuntimeDriver : MonoBehaviour
    {
        [Header("Runtime")]
        public bool run = true;

        [Header("Visual Playback")]
        [Min(0.01f)]
        [SerializeField] float visualTimeScale = 1f;

        [Header("Vehicle Spawning")]
        [Tooltip("启动时自动生成车辆以可视化交通流")]
        public bool spawnVehiclesOnStart = true;

        [Tooltip("目标车辆数量（≥20，与SUMO仿真数据同步）")]
        [Min(1)]
        [SerializeField] int targetVehicleCount = 25;

        [Tooltip("车辆数量维护检查间隔（秒）")]
        [Min(0.5f)]
        [SerializeField] float vehicleMaintainInterval = 2f;

        [Tooltip("普通车辆Prefab样式ID")]
        [SerializeField] string normalVehicleStyleId = "Truck_color03";

        SimulationRuntimeManager runtime;
        float vehicleMaintainTimer;
        bool vehiclesSpawned;
        Transform vehicleParent;

        void Awake()
        {
            runtime = new SimulationRuntimeManager();
            runtime.RebuildRoads();
        }

        void Start()
        {
            if (spawnVehiclesOnStart)
            {
                TrySpawnInitialVehicles();
            }
        }

        void Update()
        {
            if (!run || runtime == null)
            {
                return;
            }

            runtime.RunVisualStep(Time.deltaTime * visualTimeScale);

            // 延迟生成（等待路网就绪）
            if (spawnVehiclesOnStart && !vehiclesSpawned)
            {
                TrySpawnInitialVehicles();
            }

            // 周期性维护车辆数量
            if (vehiclesSpawned)
            {
                vehicleMaintainTimer += Time.deltaTime;
                if (vehicleMaintainTimer >= vehicleMaintainInterval)
                {
                    vehicleMaintainTimer = 0f;
                    MaintainVehicleCount();
                }
            }
        }

        public void RebuildRoads()
        {
            runtime?.RebuildRoads();
        }

        // ===================== 车辆生成 =====================

        /// <summary>尝试生成初始车辆批次。需要路网已构建完成。</summary>
        public void TrySpawnInitialVehicles()
        {
            var objectManager = GameServices.ObjectManager;
            var roadService = GameServices.RoadService;
            if (objectManager == null || roadService == null)
            {
                return;
            }

            // 确保路网已构建
            var roads = CollectRoads(objectManager);
            if (roads.Count == 0)
            {
                return;
            }

            // 确保RoadService已构建车道线（polylines）
            roadService.Rebuild();

            // 创建车辆父节点（保持场景层级整洁）
            if (vehicleParent == null)
            {
                var go = new GameObject("SpawnedVehicles");
                go.transform.SetParent(transform, false);
                vehicleParent = go.transform;
            }

            int spawned = 0;
            for (int i = 0; i < targetVehicleCount; i++)
            {
                if (SpawnVehicleOnRandomRoad(roads, VehicleType.Normal))
                {
                    spawned++;
                }
            }

            // 刷新VehicleService内部车辆列表
            GameServices.VehicleService?.RefreshVehicles();

            vehiclesSpawned = true;
            Debug.Log($"[SimulationRuntimeDriver] 已生成 {spawned}/{targetVehicleCount} 辆车辆");
        }

        /// <summary>维护车辆数量：补充已消失的车辆，保持与目标数量同步。</summary>
        void MaintainVehicleCount()
        {
            var objectManager = GameServices.ObjectManager;
            var vehicleService = GameServices.VehicleService;
            if (objectManager == null || vehicleService == null)
            {
                return;
            }

            // 统计当前活跃的普通车辆
            int activeNormalCount = 0;
            var vehicles = vehicleService.GetVehicles();
            for (int i = 0; i < vehicles.Count; i++)
            {
                var v = vehicles[i];
                if (v == null || v.gameObject == null) continue;
                if (!v.gameObject.activeInHierarchy) continue;
                if (v.vehicleType == VehicleType.Normal) activeNormalCount++;
            }

            if (activeNormalCount >= targetVehicleCount)
            {
                return;
            }

            // 补充缺失的车辆
            var roads = CollectRoads(objectManager);
            if (roads.Count == 0)
            {
                return;
            }

            int toSpawn = targetVehicleCount - activeNormalCount;
            int spawned = 0;
            for (int i = 0; i < toSpawn; i++)
            {
                if (SpawnVehicleOnRandomRoad(roads, VehicleType.Normal))
                {
                    spawned++;
                }
            }

            if (spawned > 0)
            {
                vehicleService.RefreshVehicles();
            }
        }

        /// <summary>在随机道路上生成一辆车辆。</summary>
        bool SpawnVehicleOnRandomRoad(List<RoadEntity> roads, VehicleType vehicleType)
        {
            if (roads == null || roads.Count == 0)
            {
                return false;
            }

            // 随机选择道路
            var road = roads[Random.Range(0, roads.Count)];
            if (road.controlPoints == null || road.controlPoints.Count < 2)
            {
                return false;
            }

            // 在道路上随机选取位置
            int segIndex = Random.Range(0, road.controlPoints.Count - 1);
            var a = road.controlPoints[segIndex];
            var b = road.controlPoints[segIndex + 1];
            float t = Random.value;
            var proj = Vector3.Lerp(a, b, t);

            var seg = b - a;
            seg.y = 0f;
            if (seg.sqrMagnitude < 0.0001f)
            {
                return false;
            }
            var tangent = seg.normalized;

            // 右侧车道偏移（右行交通）
            var right = Vector3.Cross(Vector3.up, tangent);
            var laneCenter = proj + right * SimulationConfig.VehicleLaneOffset;

            var pos = new Vector3(laneCenter.x, 0f, laneCenter.z);
            var rot = Quaternion.LookRotation(tangent, Vector3.up);

            var dto = new VehicleDTO
            {
                id = System.Guid.NewGuid().ToString(),
                category = MapCategory.Vehicle,
                styleId = vehicleType == VehicleType.Emergency ? "Police" : normalVehicleStyleId,
                position = pos,
                rotation = rot,
                vehicleType = vehicleType,
                currentRoadId = road.id,
            };

            var entity = GameServices.ObjectManager.CreateObject(dto, need_validate: false) as VehicleEntity;
            if (entity != null && entity.gameObject != null)
            {
                entity.gameObject.name = $"Vehicle_{vehicleType}_{dto.id.Substring(0, 8)}";
                if (vehicleParent != null)
                {
                    entity.gameObject.transform.SetParent(vehicleParent, true);
                }
                return true;
            }

            return false;
        }

        /// <summary>收集ObjectManager中所有有效道路。</summary>
        static List<RoadEntity> CollectRoads(ObjectManager objectManager)
        {
            var roads = new List<RoadEntity>();
            foreach (var e in objectManager.GetAllEntities())
            {
                if (e is RoadEntity r && r.controlPoints != null && r.controlPoints.Count >= 2)
                {
                    roads.Add(r);
                }
            }
            return roads;
        }
    }

    public sealed class SimulationRuntimeManager
    {
        readonly ObjectManager objectManager;
        public VehicleService Vehicles => GameServices.VehicleService;
        public TrafficService Traffic => GameServices.TrafficService;

        public SimulationRuntimeManager(ObjectManager objectManager = null)
        {
            this.objectManager = objectManager ?? GameServices.ObjectManager;
            InitializeServices();
        }

        void InitializeServices()
        {
            GameServices.RegisterRuntimeServices();

            GameServices.RoadService.Initialize(objectManager);
            GameServices.TrafficService.Initialize(objectManager);
            GameServices.VehicleService.Initialize(objectManager);
        }

        public void Release()
        {
            GameServices.ReleaseRuntimeServices();
        }

        public void RebuildRoads()
        {
            GameServices.RoadService?.Rebuild();
            GameServices.TrafficService?.EnsureTrafficLights();
        }

        public void RunSteps(
            float dt = SimulationConfig.RuntimeStepDtSeconds,
            int visualStepRepeat = -1)
        {
            int steps = visualStepRepeat > 0
                ? visualStepRepeat
                : SimulationConfig.RuntimeStepRepeat;

            if (steps <= 0)
            {
                return;
            }

            for (int i = 0; i < steps; i++)
            {
                TickOnce(dt);
            }
        }

        public void RunVisualStep(float dt)
        {
            if (dt <= 0f)
            {
                return;
            }

            TickOnce(dt);
        }

        public void TickOnce(float dt)
        {
            GameServices.RoadService?.Tick(dt);
            GameServices.TrafficService?.Tick(dt);
            GameServices.VehicleService?.Tick(dt);
            GameServices.BackendClinet?.Tick(dt); // pre is in second
        }

    }
}
