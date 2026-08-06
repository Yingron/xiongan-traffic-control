using System.Collections.Generic;
using System.Linq;
using CitySimulation.DTO;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using CitySimulation.Runtime.Simulation;
using CitySimulation.Runtime.Services.Transforms;
using CitySimulation.Geometry;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Vehicle
{
    public sealed partial class VehicleService : IEntityService
    {
        ObjectManager objectManager;
        readonly ITransformApplier applier;
        readonly List<VehicleEntity> vehicles = new();
        readonly List<VehicleEntity> emergencyVehicles = new();
        readonly Dictionary<string, bool> blockedByLeaderByVehicleId = new();
        readonly Dictionary<string, VehicleTurningState> turningStateByVehicleId = new();

        // ===========
        // Lifecycle
        // ===========

        public VehicleService(ITransformApplier applier = null)
        {
            this.applier = applier ?? new DirectTransformApplier();
        }

        public void Initialize(ObjectManager objectManager)
        {
            this.objectManager = objectManager;
            RefreshVehicles();
        }

        public void Release()
        {
            vehicles.Clear();
            emergencyVehicles.Clear();
            blockedByLeaderByVehicleId.Clear();
            turningStateByVehicleId.Clear();
            objectManager = null;
        }

        public void Tick(float dt)
        {
            var roadService = GameServices.RoadService;
            if (objectManager == null || roadService == null)
            {
                return;
            }

            RefreshFollowStates();

            for (int i = 0; i < vehicles.Count; i++)
            {
                var vehicle = vehicles[i];
                TickVehicle(vehicle, dt);
            }
        }
        
        // ===========================
        // Functions
        // ===========================

        void TickVehicle(VehicleEntity vehicle, float dt)
        {
            if (vehicle == null || vehicle.gameObject == null)
            {
                return;
            }

            var roadService = GameServices.RoadService;
            var trafficService = GameServices.TrafficService;
            if (roadService == null)
            {
                return;
            }

            if (string.IsNullOrEmpty(vehicle.currentRoadId))
            {
                return;
            }

            float travelDistance = SimulationConfig.VehicleMaxSpeed * dt;
            if (travelDistance <= 0f)
            {
                return;
            }

            // ===========================
            // validate must in order
            // ===========================

            // validate : game is done
            if (vehicle.gameStatus == GameDecisionStatus.GameCompleted)
            {
                return;
            }

            TryCompleteVehicleIfReachedTarget(vehicle);
            if (vehicle.gameStatus == GameDecisionStatus.GameCompleted)
            {
                if (turningStateByVehicleId.TryGetValue(vehicle.id, out var completedState)
                    && completedState.BackendControlling)
                {
                    ExitTurningState(vehicle, completedState);
                }
                return;
            }

            // validate : traffic light 
            if (trafficService != null)
            {
                bool canPass = HasActiveTurningLock(vehicle)
                    || trafficService.CanPassForwardSignal(vehicle.position, vehicle.rotation, vehicle.currentRoadId);
                if (!canPass)
                {
                    return;
                }
            }

            // request turning decision before movement (only emergency vehicles)
            if (trafficService != null && vehicle.vehicleType == VehicleType.Emergency)
            {
                TryControlBeforeTurning(vehicle);
            }

            // validate : read turning lock
            if (trafficService != null)
            {
                bool canTurningLockPass = ValidateReadTurningLock(vehicle);
                if (!canTurningLockPass)
                {
                    return;
                }
            }

            // validate : acquire turning lock
            if (trafficService != null)
            {
                bool lockAcquired = ValidateAcquireTurningLock(vehicle);
                if (!lockAcquired)
                {
                    return;
                }
            }

            // validate : release turning lock
            if (trafficService != null)
            {
                bool lockReleased = ValidateReleaseTurningLock(vehicle);
                if (!lockReleased)
                {
                    return;
                }
            }

            // validate : front-vehicle follow
            if (IsBlockedByLeader(vehicle))
            {
                return;
            }

            // ===========================
            // move vehicle
            // ===========================

            // move foward
            var previousPosition = vehicle.position;
            if (!roadService.TryGetTargetPose(vehicle.currentRoadId, vehicle.position, travelDistance, out var pos, out var rot))
            {
                return;
            }

            vehicle.position = pos;
            vehicle.rotation = rot;

            applier.Apply(vehicle.gameObject, pos, rot);

            // turn around
            TrySwitchRoadAtTurningPoint(vehicle, previousPosition);
        }

        void RefreshVehicles()
        {
            vehicles.Clear();
            emergencyVehicles.Clear();

            var trafficService = GameServices.TrafficService;

            if (objectManager == null)
            {
                return;
            }

            foreach (var entity in objectManager.GetAllEntities())
            {
                if (entity is VehicleEntity vehicle)
                {
                    vehicles.Add(vehicle);
                    if (vehicle.vehicleType == VehicleType.Emergency)
                    {
                        // Share the same VehicleEntity reference with vehicles (no copy).
                        emergencyVehicles.Add(vehicle);
                    }
                }
            }

            var activeIds = new HashSet<string>(vehicles.Where(v => v != null && !string.IsNullOrEmpty(v.id)).Select(v => v.id));
            foreach (var pair in turningStateByVehicleId.ToList())
            {
                if (activeIds.Contains(pair.Key))
                {
                    continue;
                }

                if (!string.IsNullOrEmpty(pair.Value.LightId))
                {
                    trafficService?.ReleaseTurningLockByVehicle(pair.Value.LightId, pair.Key);
                }

                RemoveVehicle(pair.Key);
                turningStateByVehicleId.Remove(pair.Key);
            }
        }

        // ===========================
        // forcontrol
        // ===========================
        void TryControlBeforeTurning(VehicleEntity vehicle){
            
            var trafficService = GameServices.TrafficService;
            if (trafficService == null)
            {
                return;
            }

            if (vehicle == null || string.IsNullOrEmpty(vehicle.id) || string.IsNullOrEmpty(vehicle.currentRoadId))
            {
                return;
            }

            var state = GetOrCreateTurningState(vehicle.id);

            // request decision
            if (!state.BackendControlling)
            {
                bool inBackendControlRadius = trafficService.TryGetNearestForwardLight(
                    vehicle.position,
                    vehicle.rotation,
                    vehicle.currentRoadId,
                    0f,
                    SimulationConfig.BackendControlRadius,
                    out var nearestForwardLight,
                    out _);

                if (!inBackendControlRadius)
                {
                    return;
                }

                state.BackendControlling = true;
                state.LightId = nearestForwardLight.id;
                state.Action = VehicleDecisionAction.Straight;
                state.TurningPoint = Vector3.zero;
                state.TurningLockAcquired = false;
                state.UTurnPhase = 0;
                state.UTurnOriginRoadId = null;

                SetTobeDecision(vehicle);

                return;
            }

            // exit turning state
            if (string.IsNullOrEmpty(state.LightId) || !trafficService.TryGetTrafficLightById(state.LightId, out var currentLight))
            {
                ExitTurningState(vehicle, state);
                return;
            }

            bool stillInControl = GeometryUtils.IsNearTarget(vehicle.position, currentLight.position, SimulationConfig.BackendControlRadius);
            if (!stillInControl && !IsAtomicUTurnInProgress(vehicle))
            {
                ExitTurningState(vehicle, state);
            }
        }

        // ===========================
        // validate : front-vehicle follow
        // ===========================
        void RefreshFollowStates()
        {
            if (vehicles.Count == 0)
            {
                blockedByLeaderByVehicleId.Clear();
                return;
            }

            var roadService = GameServices.RoadService;
            if (roadService == null)
            {
                blockedByLeaderByVehicleId.Clear();
                return;
            }

            float stopDistance = Mathf.Max(0f, SimulationConfig.VehicleFollowStopDistance);
            float goDistance = Mathf.Max(stopDistance + 0.0001f, SimulationConfig.VehicleFollowGoDistance);

            var activeIds = new HashSet<string>();
            var progressByRoad = new Dictionary<string, List<VehicleProgress>>();

            for (int i = 0; i < vehicles.Count; i++)
            {
                var vehicle = vehicles[i];
                if (vehicle == null || vehicle.gameObject == null || string.IsNullOrEmpty(vehicle.id) || string.IsNullOrEmpty(vehicle.currentRoadId))
                {
                    continue;
                }

                activeIds.Add(vehicle.id);

                if (!roadService.TryGetProgressS(vehicle.currentRoadId, vehicle.position, out float progressS))
                {
                    blockedByLeaderByVehicleId[vehicle.id] = false;
                    continue;
                }

                if (!progressByRoad.TryGetValue(vehicle.currentRoadId, out var list))
                {
                    list = new List<VehicleProgress>();
                    progressByRoad[vehicle.currentRoadId] = list;
                }

                list.Add(new VehicleProgress(vehicle, progressS));
            }

            foreach (var key in blockedByLeaderByVehicleId.Keys.ToList())
            {
                if (!activeIds.Contains(key))
                {
                    blockedByLeaderByVehicleId.Remove(key);
                }
            }

            foreach (var pair in progressByRoad)
            {
                string roadId = pair.Key;
                var list = pair.Value;
                if (list.Count == 0)
                {
                    continue;
                }

                if (!roadService.TryGetLaneLoopLength(roadId, out float laneLoopLength) || laneLoopLength <= 0.0001f)
                {
                    for (int i = 0; i < list.Count; i++)
                    {
                        blockedByLeaderByVehicleId[list[i].Vehicle.id] = false;
                    }

                    continue;
                }

                if (list.Count == 1)
                {
                    blockedByLeaderByVehicleId[list[0].Vehicle.id] = false;
                    continue;
                }

                list.Sort((a, b) => a.ProgressS.CompareTo(b.ProgressS));

                for (int i = 0; i < list.Count; i++)
                {
                    var self = list[i];
                    var front = list[(i + 1) % list.Count];

                    float gap = front.ProgressS - self.ProgressS;
                    if (gap <= 0f)
                    {
                        gap += laneLoopLength;
                    }

                    bool wasBlocked = blockedByLeaderByVehicleId.TryGetValue(self.Vehicle.id, out bool previousBlocked) && previousBlocked;
                    bool blocked = wasBlocked;

                    if (!wasBlocked && gap < stopDistance)
                    {
                        blocked = true;
                    }
                    else if (wasBlocked && gap > goDistance)
                    {
                        blocked = false;
                    }

                    blockedByLeaderByVehicleId[self.Vehicle.id] = blocked;
                }
            }
        }

        bool IsBlockedByLeader(VehicleEntity vehicle)
        {
            if (vehicle == null || string.IsNullOrEmpty(vehicle.id))
            {
                return false;
            }

            if (SimulationConfig.EmergencyVehiclesIgnoreLeaderBlocking
                && vehicle.vehicleType == VehicleType.Emergency)
            {
                return false;
            }

            return blockedByLeaderByVehicleId.TryGetValue(vehicle.id, out bool blocked) && blocked;
        }

        // ===========================
        // validate : game completed
        // ===========================
        void TryCompleteVehicleIfReachedTarget(VehicleEntity vehicle)
        {
            if (vehicle == null || objectManager == null || string.IsNullOrEmpty(vehicle.targetPointId))
            {
                return;
            }

            if (objectManager.GetEntity(vehicle.targetPointId) is not TargetPointEntity targetPoint || targetPoint == null)
            {
                return;
            }

            bool reachedTarget = GeometryUtils.IsNearTarget(
                vehicle.position,
                targetPoint.position,
                SimulationConfig.VehicleArrivalCompleteDistanceThreshold,
                out float currentDistanceToTarget);

            // Debug.Log($"[VehicleService] reach-check vehicle={vehicle.id} distance={currentDistanceToTarget:F3} threshold={SimulationConfig.VehicleArrivalCompleteDistanceThreshold:F3} reached={reachedTarget}");

            if (!reachedTarget)
            {
                return;
            }

            vehicle.currentRoadId = null;
            vehicle.gameStatus = GameDecisionStatus.GameCompleted;

            if (vehicle.gameObject != null)
            {
                vehicle.gameObject.SetActive(false);
            }
        }

        readonly struct VehicleProgress
        {
            public VehicleProgress(VehicleEntity vehicle, float progressS)
            {
                Vehicle = vehicle;
                ProgressS = progressS;
            }

            public VehicleEntity Vehicle { get; }
            public float ProgressS { get; }
        }

        // ===========================
        // Tools
        // ===========================

        public IReadOnlyList<VehicleEntity> GetEmergencyVehicles()
        {
            return emergencyVehicles;
        }

        public IReadOnlyList<VehicleEntity> GetVehicles()
        {
            return vehicles;
        }


    }
}
