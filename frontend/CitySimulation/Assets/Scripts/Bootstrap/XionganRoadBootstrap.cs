using CitySimulation.Builder;
using CitySimulation.GameObjects;
using CitySimulation.Global;
using UnityEngine;

namespace CitySimulation.Bootstrap
{
    /// <summary>
    /// Scene bootstrapper: drop this into Scenes/City.unity as a GameObject and
    /// it will automatically build the xiongan 30-intersection road network
    /// on scene Awake (right after GameServices initializes ObjectManager).
    ///
    /// To use:
    ///   1. Open Scenes/City.unity in Unity
    ///   2. Create a new empty GameObject named "XionganRoadBootstrap"
    ///   3. Drag this script as a component
    ///   4. (Optional) Tick "Build On Awake" to auto-build.
    ///   5. Press Play — road network + 30 traffic lights will appear.
    ///
    /// Or trigger via the menu 雄安路网 / 构建 xiongan_30 ... instead.
    /// </summary>
    [DisallowMultipleComponent]
    public class XionganRoadBootstrap : MonoBehaviour
    {
        [Header("Settings")]
        [Tooltip("Name of the JSON file (without extension) under Assets/Scripts/Maps.")]
        public string mapId = "xiongan_30";

        [Tooltip("If true, BuildFromJson is invoked on Awake (Play mode).")]
        public bool buildOnAwake = true;

        [Tooltip("Rebuild every time this component is Enabled in Editor (useful for quick iteration).")]
        public bool rebuildOnEnableInEditMode = false;

        [Tooltip("Frame the complete xiongan_30 map in the Game camera after building.")]
        public bool frameCameraAfterBuild = true;

        [Range(1.0f, 2.0f)]
        public float cameraPadding = 1.12f;

        [Header("Runtime State (read-only)")]
        [SerializeField] private int _roads;
        [SerializeField] private int _trafficLights;
        [SerializeField] private string _statusMessage;

        public int Roads => _roads;
        public int TrafficLights => _trafficLights;
        public string StatusMessage => _statusMessage;

        private void Awake()
        {
            if (!Application.isPlaying) return;
            if (buildOnAwake) BuildNow();
        }

        private void OnEnable()
        {
            if (!rebuildOnEnableInEditMode) return;
            if (Application.isPlaying) return;
            // Edit-mode build: use standalone ObjectManager so we don't need GameServices
            BuildNowStandalone();
        }

        /// <summary>Button-like API: build using GameServices.ObjectManager (Play mode).</summary>
        [ContextMenu("Build Xiongan 30 (use GameServices)")]
        public void BuildNow()
        {
            var builder = new RoadNetworkBuilder();
            try
            {
                var report = builder.BuildFromJson(mapId);
                _roads = report.roads;
                _trafficLights = report.trafficLights;
                _statusMessage =
                    $"[OK] map={mapId} roads={_roads} tls={_trafficLights}/{report.intersectionsExpected}";
                if (frameCameraAfterBuild) FrameMainCamera(report);
            }
            catch (System.Exception ex)
            {
                _statusMessage = $"[FAIL] {ex.Message}";
                Debug.LogException(ex, this);
            }
        }

        private void FrameMainCamera(BuildReport report)
        {
            var camera = Camera.main;
            if (camera == null)
            {
                Debug.LogWarning("[XionganRoadBootstrap] Main Camera not found; map framing skipped.");
                return;
            }

            var center = (report.boundsMin + report.boundsMax) * 0.5f;
            var size = report.boundsMax - report.boundsMin;
            camera.orthographic = true;
            camera.transform.position = new Vector3(center.x, Mathf.Max(1000f, size.magnitude), center.z);
            camera.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
            camera.orthographicSize = Mathf.Max(
                size.z * 0.5f,
                size.x * 0.5f / Mathf.Max(0.1f, camera.aspect)) * cameraPadding;
            camera.nearClipPlane = 0.3f;
            camera.farClipPlane = Mathf.Max(3000f, camera.transform.position.y + 1000f);
            Debug.Log(
                $"[XionganRoadBootstrap] Camera framed at {camera.transform.position}, " +
                $"orthographicSize={camera.orthographicSize:F1}.");
        }

        /// <summary>Edit-mode safe build (does not require GameServices).</summary>
        [ContextMenu("Build Xiongan 30 (standalone / edit mode)")]
        public void BuildNowStandalone()
        {
            var builder = new RoadNetworkBuilder();
            try
            {
                var factory = new PrefabFactory();
                var om = new ObjectManager(factory);
                var path = RoadNetworkBuilder.ResolveJsonPath(mapId);
                if (string.IsNullOrEmpty(path))
                {
                    _statusMessage = $"[FAIL] Cannot locate {mapId}.json under Assets/Scripts/Maps";
                    Debug.LogError(_statusMessage, this);
                    return;
                }
                var report = builder.BuildFromJsonFullPath(path, om);
                _roads = report.roads;
                _trafficLights = report.trafficLights;
                _statusMessage =
                    $"[OK][standalone] map={mapId} roads={_roads} tls={_trafficLights}/{report.intersectionsExpected}";
            }
            catch (System.Exception ex)
            {
                _statusMessage = $"[FAIL] {ex.Message}";
                Debug.LogException(ex, this);
            }
        }
    }
}
