using CitySimulation.DTO;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Geometry;
using CitySimulation.Global;
using CitySimulation.Runtime.Simulation;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Vehicle
{
    public sealed partial class VehicleService
    {
        // ====================
        // Turning -- Lock
        // ====================
        bool ValidateReadTurningLock(VehicleEntity vehicle)
        {
            var trafficService = GameServices.TrafficService;
            if (trafficService == null)
            {
                return true;
            }

            if (vehicle == null || string.IsNullOrEmpty(vehicle.id) || string.IsNullOrEmpty(vehicle.currentRoadId))
            {
                return true;
            }

            if (HasActiveTurningLock(vehicle))
            {
                return true;
            }

            if (!trafficService.TryGetNearestForwardLight(
                    vehicle.position,
                    vehicle.rotation,
                    vehicle.currentRoadId,
                    SimulationConfig.SemaphoreControlRingInnerRadius,
                    SimulationConfig.SemaphoreControlRingOuterRadius,
                    out var nearestForwardLight,
                    out _))
            {
                return true;
            }

            int directionSign = 1;
            var roadService = GameServices.RoadService;
            if (roadService != null)
            {
                roadService.TryGetDirectionSign(vehicle.currentRoadId, vehicle.position, vehicle.rotation, out directionSign);
            }
            return trafficService.CanEnterTurningLock(nearestForwardLight.id, vehicle.currentRoadId, directionSign);
        }

        bool ValidateAcquireTurningLock(VehicleEntity vehicle)
        {
            var trafficService = GameServices.TrafficService;
            if (trafficService == null)
            {
                return true;
            }

            if (vehicle == null || string.IsNullOrEmpty(vehicle.id) || string.IsNullOrEmpty(vehicle.currentRoadId))
            {
                return true;
            }

            if (!turningStateByVehicleId.TryGetValue(vehicle.id, out var state) || !state.BackendControlling)
            {
                return true;
            }

            bool needsTurningLock = state.Action == VehicleDecisionAction.Left || state.Action == VehicleDecisionAction.UTurn;
            if (!needsTurningLock)
            {
                return true;
            }

            if (state.TurningLockAcquired)
            {
                return true;
            }

            if (string.IsNullOrEmpty(state.LightId) || !trafficService.TryGetTrafficLightById(state.LightId, out var lockLight))
            {
                return false;
            }

            if (state.Action == VehicleDecisionAction.UTurn)
            {
                if (!trafficService.TryAcquireUTurnLock(state.LightId, vehicle.id))
                {
                    return false;
                }
                state.TurningLockAcquired = true;
                return true;
            }

            int directionSign = 1;
            var roadService = GameServices.RoadService;
            if (roadService != null)
            {
                roadService.TryGetDirectionSign(vehicle.currentRoadId, vehicle.position, vehicle.rotation, out directionSign);
            }
            if (!trafficService.TryAcquireTurningLock(lockLight.id, vehicle.currentRoadId, directionSign, vehicle.id))
            {
                return false;
            }

            state.TurningLockAcquired = true;
            return true;
        }

        bool ValidateReleaseTurningLock(VehicleEntity vehicle)
        {
            var trafficService = GameServices.TrafficService;
            if (trafficService == null)
            {
                return true;
            }

            if (vehicle == null || string.IsNullOrEmpty(vehicle.id) || string.IsNullOrEmpty(vehicle.currentRoadId))
            {
                return true;
            }

            if (!turningStateByVehicleId.TryGetValue(vehicle.id, out var state) || !state.BackendControlling)
            {
                return true;
            }

            if (state.Action != VehicleDecisionAction.Straight || !state.TurningLockAcquired)
            {
                return true;
            }

            if (string.IsNullOrEmpty(state.LightId) || !trafficService.TryGetTrafficLightById(state.LightId, out var light))
            {
                return true;
            }

            float distanceToLight = (vehicle.position - light.position).magnitude;
            if (distanceToLight <= SimulationConfig.SemaphoreKeepRadius)
            {
                return true;
            }

            // Use ReleaseAll to avoid direction mismatch after turning.
            trafficService.ReleaseTurningLockByVehicle(state.LightId, vehicle.id);
            state.TurningLockAcquired = false;
            return true;
        }

        // ====================
        // Turning -- Try switch road
        // ====================
        void TrySwitchRoadAtTurningPoint(VehicleEntity vehicle, Vector3 previousPosition)
        {
            var trafficService = GameServices.TrafficService;
            if (trafficService == null)
            {
                return;
            }

            if (vehicle == null || string.IsNullOrEmpty(vehicle.id))
            {
                return;
            }

            if (!turningStateByVehicleId.TryGetValue(vehicle.id, out var state))
            {
                return;
            }

            if (!state.BackendControlling)
            {
                return;
            }

            if (string.IsNullOrEmpty(state.LightId) || !trafficService.TryGetTrafficLightById(state.LightId, out var light))
            {
                return;
            }

            bool atomicUTurn = state.Action == VehicleDecisionAction.UTurn;
            VehicleDecisionAction action = atomicUTurn ? VehicleDecisionAction.Left : state.Action;

            if (action != VehicleDecisionAction.Left && action != VehicleDecisionAction.Right)
            {
                return;
            }

            string targetRoadId;
            if (atomicUTurn && state.UTurnPhase == 2)
            {
                targetRoadId = state.UTurnOriginRoadId;
                if (string.IsNullOrEmpty(targetRoadId)
                    || string.Equals(targetRoadId, vehicle.currentRoadId, System.StringComparison.Ordinal))
                {
                    return;
                }
            }
            else if (!trafficService.TryGetAlternativeRoadId(light, vehicle.currentRoadId, out targetRoadId))
            {
                return;
            }

            if (state.TurningPoint == Vector3.zero)
            {
                Vector3 turningPoint;
                bool foundTurningPoint = atomicUTurn
                    ? trafficService.TryGetAtomicUTurnTurningPoint(
                        light,
                        vehicle.position,
                        vehicle.rotation,
                        targetRoadId,
                        state.UTurnPhase,
                        out turningPoint)
                    : trafficService.TryGetTurningPointOnTargetRightLane(
                        light,
                        vehicle.position,
                        vehicle.rotation,
                        targetRoadId,
                        action,
                        out turningPoint);
                if (foundTurningPoint)
                {
                    state.TurningPoint = turningPoint;

                    // // <Debug>
                    // // Debug helper: create or move a small cube at the turning point
                    // try
                    // {
                    //     string debugName = $"Debug_TurningPoint_{vehicle.id}";
                    //     var existing = GameObject.Find(debugName);
                    //     if (existing != null)
                    //     {
                    //         existing.transform.position = turningPoint;
                    //     }
                    //     else
                    //     {
                    //         var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    //         go.name = debugName;
                    //         go.transform.position = turningPoint;
                    //         go.transform.localScale = Vector3.one * 0.5f;
                    //         var rend = go.GetComponent<Renderer>();
                    //         if (rend != null)
                    //         {
                    //             rend.material.color = Color.yellow;
                    //         }
                    //     }
                    // }
                    // catch { }

                    // // </Debug>
                }
            }

            if (state.TurningPoint == Vector3.zero)
            {
                return;
            }

            if (IsNearTargetOrPassed(previousPosition, vehicle.position, state.TurningPoint, SimulationConfig.VehicleTurnSwitchRoadDistance))
            {
                // // <Debug>
                // // Debug helper: turning
                // Debug.Log($"Vehicle {vehicle.id} is turning");
                // // </Debug>

                vehicle.currentRoadId = targetRoadId;
                state.TurningPoint = Vector3.zero;

                if (atomicUTurn && state.UTurnPhase == 1)
                {
                    // Keep the backend action atomic and hidden. Internally the
                    // vehicle now performs the second left turn back onto the
                    // origin road in the opposite direction.
                    state.UTurnPhase = 2;
                }
                else
                {
                    state.Action = VehicleDecisionAction.Straight;
                    state.UTurnPhase = 0;
                    state.UTurnOriginRoadId = null;
                }
            }
        }

        bool IsAtomicUTurnInProgress(VehicleEntity vehicle)
        {
            return vehicle != null
                && !string.IsNullOrEmpty(vehicle.id)
                && turningStateByVehicleId.TryGetValue(vehicle.id, out var state)
                && state.BackendControlling
                && state.Action == VehicleDecisionAction.UTurn
                && state.UTurnPhase >= 1;
        }

        bool HasActiveTurningLock(VehicleEntity vehicle)
        {
            return vehicle != null
                && !string.IsNullOrEmpty(vehicle.id)
                && turningStateByVehicleId.TryGetValue(vehicle.id, out var state)
                && state.BackendControlling
                && state.TurningLockAcquired;
        }

        bool IsNearTargetOrPassed(Vector3 previousPosition, Vector3 currentPosition, Vector3 targetPosition, float radius)
        {
            float safeRadius = Mathf.Max(0f, radius);
            if (GeometryUtils.IsNearTarget(currentPosition, targetPosition, safeRadius))
            {
                return true;
            }

            return GeometryUtils.IsPointNearSegmentXZ(targetPosition, previousPosition, currentPosition, safeRadius);
        }

        // ====================
        // Turning -- Turning State
        // ====================
        VehicleTurningState GetOrCreateTurningState(string vehicleId)
        {
            if (!turningStateByVehicleId.TryGetValue(vehicleId, out var state))
            {
                state = new VehicleTurningState();
                turningStateByVehicleId[vehicleId] = state;
            }

            return state;
        }

        void ExitTurningState(VehicleEntity vehicle, VehicleTurningState state)
        {
            var trafficService = GameServices.TrafficService;

            if (!string.IsNullOrEmpty(state.LightId))
            {
                trafficService?.ReleaseTurningLockByVehicle(state.LightId, vehicle.id);
            }

            if (vehicle.vehicleType == VehicleType.Emergency)
            {
                RemoveVehicle(vehicle.id);
                if (vehicle.gameStatus != GameDecisionStatus.GameCompleted)
                {
                    vehicle.gameStatus = GameDecisionStatus.NoDecisionNeeded;
                }
            }

            state.LightId = null;
            state.BackendControlling = false;
            state.Action = VehicleDecisionAction.Straight;
            state.TurningPoint = Vector3.zero;
            state.TurningLockAcquired = false;
            state.UTurnPhase = 0;
            state.UTurnOriginRoadId = null;
        }

        sealed class VehicleTurningState
        {
            public bool BackendControlling;
            public string LightId;
            public VehicleDecisionAction Action;
            public Vector3 TurningPoint;
            public bool TurningLockAcquired;
            public int UTurnPhase;
            public string UTurnOriginRoadId;
        }
    }
}
