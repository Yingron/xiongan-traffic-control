using CitySimulation.GameObjects;
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

        SimulationRuntimeManager runtime;

        void Awake()
        {
            runtime = new SimulationRuntimeManager();
            runtime.RebuildRoads();
        }

        void Update()
        {
            if (!run)
            {
                return;
            }

            runtime.RunVisualStep(Time.deltaTime * visualTimeScale);
        }

        public void RebuildRoads()
        {
            runtime?.RebuildRoads();
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
