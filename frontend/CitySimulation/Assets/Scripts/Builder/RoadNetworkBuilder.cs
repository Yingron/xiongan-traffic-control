using System;
using System.Collections.Generic;
using System.IO;
using CitySimulation.DTO;
using CitySimulation.GameObjects;
using CitySimulation.Global;
using UnityEngine;

namespace CitySimulation.Builder
{
    /// <summary>
    /// Parses xiongan_30.json (6x5 grid with 30 intersections, category 2 = building,
    /// category 4 = traffic light)
    /// and rebuilds the map inside the current scene via the existing ObjectManager
    /// pipeline (PrefabFactory + Resources/{Road,TarfficLight}/section|Empty_TrafficLight).
    ///
    /// Run-time usage:
    ///   var builder = new RoadNetworkBuilder();
    ///   builder.BuildFromJson("xiongan_30");   // lives in Assets/Scripts/Maps
    ///   // or
    ///   builder.BuildFromJsonFullPath(@"C:\full\path\xiongan_30.json");
    ///
    /// For editor usage, see RoadNetworkBuilderEditor.cs (menu: 雄安路网 / 构建 xiongan_30 30路口).
    /// </summary>
    [Serializable]
    public class RoadNetworkBuilder
    {
        [SerializeField] private string _lastLoadedMapId;
        [SerializeField] private int _roadsCreated;
        [SerializeField] private int _trafficLightsCreated;

        public string LastLoadedMapId => _lastLoadedMapId;
        public int RoadsCreated => _roadsCreated;
        public int TrafficLightsCreated => _trafficLightsCreated;

        /// <summary>
        /// Resolve the xiongan_30.json path inside the Unity project. During edit mode
        /// or player builds we first search the canonical Assets/Scripts/Maps folder,
        /// then try Application.streamingAssetsPath for shipped JSONs.
        /// </summary>
        public static string ResolveJsonPath(string mapId)
        {
            var safeId = string.IsNullOrEmpty(mapId) ? "xiongan_30" : mapId;
            if (!safeId.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
                safeId += ".json";

            // 1) Assets/Scripts/Maps (MapManager convention)
            var scriptsMaps = Path.Combine(Application.dataPath, "Scripts", "Maps");
            var p = Path.Combine(scriptsMaps, safeId);
            if (File.Exists(p)) return p;

            // 2) project-level Maps folder (fallback during Editor runs)
            var projectMaps = Path.GetFullPath(
                Path.Combine(Application.dataPath, "..", "Scripts", "Maps"));
            p = Path.Combine(projectMaps, safeId);
            if (File.Exists(p)) return p;

            // 3) StreamingAssets
            p = Path.Combine(Application.streamingAssetsPath, safeId);
            if (File.Exists(p)) return p;

            return null;
        }

        /// <summary>Build from a map id inside Assets/Scripts/Maps (default "xiongan_30").</summary>
        public BuildReport BuildFromJson(string mapId = "xiongan_30", ObjectManager objectManager = null)
        {
            var path = ResolveJsonPath(mapId);
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
                throw new FileNotFoundException(
                    $"Cannot find '{mapId}.json'. Place it under Assets/Scripts/Maps.",
                    mapId);
            return BuildFromJsonFullPath(path, objectManager);
        }

        /// <summary>Build from an absolute JSON path.</summary>
        public BuildReport BuildFromJsonFullPath(string fullPath, ObjectManager objectManager = null)
        {
            if (!File.Exists(fullPath))
                throw new FileNotFoundException(fullPath);
            var json = File.ReadAllText(fullPath);
            var snapshot = ParseSnapshot(json);
            return ImportSnapshot(snapshot, Path.GetFileNameWithoutExtension(fullPath), objectManager);
        }

        // --------------- json parsing (category mapping) ----------------
        //
        // xiongan_30.json uses numeric "category" but our DTOs use MapCategory enum.
        //   1 => Road
        //   2 => Building
        //   4 => TrafficLight
        // We parse through a loose intermediate struct to keep JsonUtility happy.
        [Serializable]
        private struct Vec3Data
        {
            public float x;
            public float y;
            public float z;
            public Vector3 Value => new Vector3(x, y, z);
        }

        [Serializable]
        private struct QuatData
        {
            public float x;
            public float y;
            public float z;
            public float w;
            public Quaternion Value => new Quaternion(x, y, z, w);
        }

        [Serializable]
        private struct RoadRaw
        {
            public string id;
            public int category;
            public string styleId;
            public Vec3Data position;
            public QuatData rotation;
            public List<Vec3Data> controlPoints;
        }

        [Serializable]
        private struct TrafficLightRaw
        {
            public string id;
            public int category;
            public string styleId;
            public Vec3Data position;
            public QuatData rotation;
            public List<string> controlledRoadIds;
            public string currentGreenRoadId;
            public float timeInPhase;
        }

        [Serializable]
        private struct BuildingRaw
        {
            public string id;
            public int category;
            public string styleId;
            public Vec3Data position;
            public QuatData rotation;
            public Vec3Data size;
        }

        [Serializable]
        private class SnapshotRaw
        {
            public List<RoadRaw> roads = new List<RoadRaw>();
            public List<BuildingRaw> buildings = new List<BuildingRaw>();
            public List<TrafficLightRaw> trafficLights = new List<TrafficLightRaw>();
        }

        [Serializable]
        private class SnapshotWrapperRaw
        {
            public SnapshotRaw snapshot = new SnapshotRaw();
        }

        private static ObjectManager.MapSnapshot ParseSnapshot(string json)
        {
            var wrapper = JsonUtility.FromJson<SnapshotWrapperRaw>(json) ?? new SnapshotWrapperRaw();
            var snap = wrapper.snapshot ?? new SnapshotRaw();
            var result = new ObjectManager.MapSnapshot();

            // ----- roads (category = 1) -----
            if (snap.roads != null)
            {
                foreach (var raw in snap.roads)
                {
                    var dto = new RoadDTO
                    {
                        id = string.IsNullOrEmpty(raw.id) ? Guid.NewGuid().ToString() : raw.id,
                        category = MapCategory.Road,
                        styleId = raw.styleId,
                        position = raw.position.Value,
                        rotation = IdentityIfZero(raw.rotation.Value),
                    };
                    if (raw.controlPoints != null)
                    {
                        foreach (var cp in raw.controlPoints)
                            dto.controlPoints.Add(new Vector3(cp.x, cp.y, cp.z));
                    }
                    result.roads.Add(dto);
                }
            }

            // ----- buildings (category = 2) -----
            if (snap.buildings != null)
            {
                foreach (var raw in snap.buildings)
                {
                    result.buildings.Add(new BuildingDTO
                    {
                        id = string.IsNullOrEmpty(raw.id) ? Guid.NewGuid().ToString() : raw.id,
                        category = MapCategory.Building,
                        styleId = raw.styleId,
                        position = raw.position.Value,
                        rotation = IdentityIfZero(raw.rotation.Value),
                        size = raw.size.Value,
                    });
                }
            }

            // ----- traffic lights (category = 4) -----
            if (snap.trafficLights != null)
            {
                foreach (var raw in snap.trafficLights)
                {
                    // JSON 坐标约定: x=网格列(0-800), y=高度(道路0, 交通灯5), z=网格行(0-1000)
                    // Unity 坐标约定: X=水平, Y=高度, Z=前进
                    // 直接映射: Unity(X,Y,Z) = JSON(x,y,z)
                    var dto = new TrafficLightDTO
                    {
                        id = string.IsNullOrEmpty(raw.id) ? Guid.NewGuid().ToString() : raw.id,
                        category = MapCategory.TrafficLight,
                        styleId = string.IsNullOrEmpty(raw.styleId) ? "Empty_TrafficLight" : raw.styleId,
                        position = raw.position.Value,
                        rotation = IdentityIfZero(raw.rotation.Value),
                        currentGreenRoadId = raw.currentGreenRoadId,
                        timeInPhase = raw.timeInPhase,
                    };
                    if (raw.controlledRoadIds != null)
                    {
                        foreach (var rid in raw.controlledRoadIds)
                            dto.controlledRoadIds.Add(rid);
                    }
                    result.trafficLights.Add(dto);
                }
            }

            return result;
        }

        private static Quaternion IdentityIfZero(Quaternion q)
        {
            return q.x == 0f && q.y == 0f && q.z == 0f && q.w == 0f
                ? Quaternion.identity
                : q;
        }

        // --------------- import into ObjectManager ----------------
        private BuildReport ImportSnapshot(ObjectManager.MapSnapshot snap, string mapId, ObjectManager objectManager)
        {
            var om = objectManager ?? GameServices.ObjectManager;
            if (om == null)
                throw new InvalidOperationException(
                    "ObjectManager unavailable. Ensure GameServices initializes the scene, " +
                    "or pass an explicit ObjectManager instance.");

            om.ImportAll(snap);

            _lastLoadedMapId = mapId;
            _roadsCreated = snap.roads != null ? snap.roads.Count : 0;
            _trafficLightsCreated = snap.trafficLights != null ? snap.trafficLights.Count : 0;

            var report = new BuildReport
            {
                mapId = mapId,
                roads = _roadsCreated,
                trafficLights = _trafficLightsCreated,
                intersectionsExpected = _trafficLightsCreated,
                boundsMin = ComputeBounds(snap, true),
                boundsMax = ComputeBounds(snap, false),
            };
            report.Validate();

            Debug.Log(
                $"[RoadNetworkBuilder] Built '{mapId}': " +
                $"{report.roads} roads, {report.trafficLights}/{report.intersectionsExpected} traffic lights " +
                $"| bounds {report.boundsMin:F1} ~ {report.boundsMax:F1}");

            return report;
        }

        private static Vector3 ComputeBounds(ObjectManager.MapSnapshot snap, bool min)
        {
            Vector3? any = null;
            void Accumulate(Vector3 p)
            {
                if (!any.HasValue) any = p;
                else any = min ? Vector3.Min(any.Value, p) : Vector3.Max(any.Value, p);
            }
            if (snap.trafficLights != null)
                foreach (var tl in snap.trafficLights) Accumulate(tl.position);
            if (snap.roads != null)
            {
                foreach (var r in snap.roads)
                {
                    Accumulate(r.position);
                    if (r.controlPoints != null)
                        foreach (var cp in r.controlPoints) Accumulate(cp);
                }
            }
            if (snap.buildings != null)
                foreach (var building in snap.buildings) Accumulate(building.position);
            return any ?? Vector3.zero;
        }
    }

    [Serializable]
    public class BuildReport
    {
        public string mapId;
        public int roads;
        public int trafficLights;
        public int intersectionsExpected = 30;
        public Vector3 boundsMin;
        public Vector3 boundsMax;
        public List<string> warnings = new List<string>();
        public List<string> errors = new List<string>();

        public bool IsValid => errors.Count == 0;

        public void Validate()
        {
            if (trafficLights != intersectionsExpected)
                warnings.Add($"路口数 {trafficLights} ≠ 预期 {intersectionsExpected}。请确认 JSON 的 trafficLights 段完整。");
            if (roads <= 0)
                errors.Add("道路数为0，JSON roads段可能缺失或解析失败。");
        }
    }
}
