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
        public static BackendClinet BackendClinet { get; private set; }
        public static VehicleService VehicleService { get; private set; }

        public static void RegisterRuntimeServices()
        {
            RoadService ??= new RoadService();
            TrafficService ??= new TrafficService();
            BackendClinet ??= new BackendClinet();
            VehicleService ??= new VehicleService();
        }

        public static void ReleaseRuntimeServices()
        {
            VehicleService?.Release();
            TrafficService?.Release();
            RoadService?.Release();
            BackendClinet?.Release();

            VehicleService = null;
            TrafficService = null;
            RoadService = null;
            BackendClinet = null;
        }
    }
}
