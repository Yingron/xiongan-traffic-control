using CitySimulation.GameObjects;
using CitySimulation.Runtime.Services.Road;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;
using CitySimulation.Runtime.Simulation;

namespace CitySimulation.Global
{
    /// <summary>
    /// Simple service locator to share PrefabFactory and ObjectManager across UI tools.
    /// Ensures roads/vehicles/buildings query the same ObjectManager instance.
    /// </summary>
    public static class GameServices
    {
        public static readonly PrefabFactory Prefabs = new PrefabFactory();
        public static readonly ObjectManager ObjectManager = new ObjectManager(Prefabs);
        public static readonly MapManager MapManager = new MapManager(ObjectManager);

        public static RoadService RoadService { get; private set; }
        public static TrafficService TrafficService { get; private set; }
        public static BackendClinet BackendClinet { get; set; }
        public static VehicleService VehicleService { get; private set; }

        /// <summary>Bridge server host for TCP connection (set before RegisterRuntimeServices).</summary>
        public static string BridgeHost { get; set; } = "127.0.0.1";
        /// <summary>Bridge server port for TCP connection.</summary>
        public static int BridgePort { get; set; } = 5000;
        /// <summary>Whether to use real BridgeClient (true) or TestMock (false).</summary>
        public static bool UseBridgeBackend { get; set; } = false;

        public static void RegisterRuntimeServices()
        {
            RoadService ??= new RoadService();
            TrafficService ??= new TrafficService();
            VehicleService ??= new VehicleService();

            if (BackendClinet == null)
            {
                BackendClinet = new BackendClinet();
                var mode = UseBridgeBackend
                    ? BackendClinet.BackendMode.BridgeTcp
                    : BackendClinet.BackendMode.TestMock;
                BackendClinet.Initialize(mode, BridgeHost, BridgePort);
            }
        }

        public static void ReleaseRuntimeServices()
        {
            VehicleService?.Release();
            TrafficService?.Release();
            RoadService?.Release();
            BackendClinet?.Release();
            BackendClinet?.Dispose();

            VehicleService = null;
            TrafficService = null;
            RoadService = null;
            BackendClinet = null;
        }
    }
}
