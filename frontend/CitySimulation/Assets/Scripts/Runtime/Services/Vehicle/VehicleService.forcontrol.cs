using System;
using System.Collections.Generic;
using UnityEngine;
using CitySimulation.DTO;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using CitySimulation.Geometry;

namespace CitySimulation.Runtime.Services.Vehicle
{
    public enum VehicleDecisionAction
    {
        NoOperation,
        Straight,
        Left,
        Right,
        UTurn
    }

    public readonly struct VehicleObverse
    {
        public VehicleObverse(
            float positionX,
            float positionZ,
            float sinThetaToTarget,
            float cosThetaToTarget,
            float distanceToTarget,
            GameDecisionStatus gameStatus,
            int objectType)
        {
            PositionX = positionX;
            PositionZ = positionZ;
            SinThetaToTarget = sinThetaToTarget;
            CosThetaToTarget = cosThetaToTarget;
            DistanceToTarget = distanceToTarget;
            GameStatus = gameStatus;
            ObjectType = objectType;
        }

        public float PositionX { get; }
        public float PositionZ { get; }
        public float SinThetaToTarget { get; }
        public float CosThetaToTarget { get; }
        public float DistanceToTarget { get; }
        public GameDecisionStatus GameStatus { get; }
        public int ObjectType { get; }
    }

    public sealed partial class VehicleService
    {

        // obverse
        public List<VehicleObverse> GetEmergencyVehicleObverse()
        {
            var VehicleObverseList = new List<VehicleObverse>(emergencyVehicles.Count);

            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null || string.IsNullOrEmpty(vehicle.id))
                {
                    continue;
                }

                Vector3 targetPosition = vehicle.position;
                if (!string.IsNullOrEmpty(vehicle.targetPointId)
                    && objectManager != null
                    && objectManager.GetEntity(vehicle.targetPointId) is TargetPointEntity tp
                    && tp != null)
                {
                    targetPosition = tp.position;
                }

                GeometryUtils.GetHeadingToTargetSinCosXZ(
                    vehicle.position,
                    vehicle.rotation,
                    targetPosition,
                    out float sinTheta,
                    out float cosTheta,
                    out float distance);

                VehicleObverseList.Add(new VehicleObverse(
                    vehicle.position.x,
                    vehicle.position.z,
                    sinTheta,
                    cosTheta,
                    distance,
                    vehicle.gameStatus,
                    0));
            }

            return VehicleObverseList;
        }
        
        // action
        public void RemoveVehicle(string vehicleId)
        {
            if (string.IsNullOrEmpty(vehicleId))
            {
                return;
            }

            rewardStateByVehicleId.Remove(vehicleId);
        }
        
        public void SetTobeDecision(VehicleEntity vehicle)
        {
            if (vehicle == null)
            {
                return;
            }

            vehicle.gameStatus = GameDecisionStatus.NeedDecision;
        }

        public int[] BuildVehicleAvailActionMask(GameDecisionStatus status, int actionSize)
        {
            if (actionSize < 0)
            {
                actionSize = 0;
            }

            var mask = new int[actionSize];
            if (status == GameDecisionStatus.NeedDecision)
            {
                // NeedDecision: NoOperation is not allowed for vehicle.
                // vehicle: 1=Straight, 2=Left, 3=Right, 4=UTurn
                for (int action = 1; action <= 4 && action < actionSize; action++)
                {
                    mask[action] = 1;
                }
                return mask;
            }

            // NoDecisionNeeded / GameCompleted: only 0=NoOperation
            if (actionSize > 0)
            {
                mask[0] = 1;
            }

            return mask;
        }

        public void ApplyVehicleDecision(IReadOnlyList<VehicleDecisionAction> actions)
        {
            if (emergencyVehicles.Count == 0)
            {
                return;
            }

            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null || string.IsNullOrEmpty(vehicle.id))
                {
                    continue;
                }

                var action = VehicleDecisionAction.NoOperation;
                if (actions != null && i < actions.Count)
                {
                    action = actions[i];
                }

                if (action == VehicleDecisionAction.NoOperation)
                {
                    continue;
                }

                ApplyVehicleDecisionById(vehicle.id, action);
            }
        }

        public void ApplyVehicleDecision(IReadOnlyList<int> backendActions)
        {
            if (backendActions == null)
            {
                ApplyVehicleDecision((IReadOnlyList<VehicleDecisionAction>)null);
                return;
            }

            var mappedActions = new List<VehicleDecisionAction>(backendActions.Count);
            for (int i = 0; i < backendActions.Count; i++)
            {
                mappedActions.Add(MapVehicleBackendAction(backendActions[i]));
            }

            ApplyVehicleDecision(mappedActions);
        }

        static VehicleDecisionAction MapVehicleBackendAction(int backendAction)
        {
            if (backendAction < 0 || backendAction >= SimulationConfig.UnifiedAgentActionSpaceSize)
            {
                return VehicleDecisionAction.NoOperation;
            }

            return backendAction switch
            {
                0 => VehicleDecisionAction.NoOperation,
                1 => VehicleDecisionAction.Straight,
                2 => VehicleDecisionAction.Left,
                3 => VehicleDecisionAction.Right,
                4 => VehicleDecisionAction.UTurn,
                _ => VehicleDecisionAction.NoOperation,
            };
        }

        public void ApplyVehicleDecisionById(string vehicleId, VehicleDecisionAction action)
        {
            if (string.IsNullOrEmpty(vehicleId))
            {
                return;
            }

            if (!turningStateByVehicleId.TryGetValue(vehicleId, out var state))
            {
                return;
            }

            // // <Debug>
            // // log decision
            // Debug.Log($"SetDecisionActionByVehicleid: vehicle={vehicleId}, action={action}");
            // // </Debug>

            var vehicle = objectManager?.GetEntity(vehicleId) as VehicleEntity;
            state.Action = action;
            state.TurningPoint = Vector3.zero;
            state.UTurnPhase = action == VehicleDecisionAction.UTurn ? 1 : 0;
            state.UTurnOriginRoadId = action == VehicleDecisionAction.UTurn && vehicle != null
                ? vehicle.currentRoadId
                : null;

            // ========================== for lock==========================
            bool needsTurningLock = action == VehicleDecisionAction.Left || action == VehicleDecisionAction.UTurn;
            if (!needsTurningLock)
            {
                state.TurningLockAcquired = false;
            }
            // ========================== end========================

            if (vehicle != null
                && vehicle.gameStatus != GameDecisionStatus.GameCompleted)
            {
                vehicle.gameStatus = GameDecisionStatus.NoDecisionNeeded;
            }
        }
    
        // reward
        sealed class VehicleRewardState
        {
            public float ExpectedTime;
            public float StartElapsedTime;
            public float LastDistance;
            public GameDecisionStatus LastStatus;
        }

        readonly Dictionary<string, VehicleRewardState> rewardStateByVehicleId = new();

        /// <summary>
        /// Compute reward of current decision step for each emergency vehicle.
        /// Returned list is aligned with emergencyVehicles order.
        /// elapsedTimeSeconds should be episode/simulation elapsed time in seconds.
        /// </summary>
        public List<float> GetCurrentStepTotalReward(float elapsedTimeSeconds)
        {
            if (elapsedTimeSeconds < 0f)
            {
                elapsedTimeSeconds = 0f;
            }

            var rewards = new List<float>(emergencyVehicles.Count);

            if (emergencyVehicles.Count == 0)
            {
                return rewards;
            }

            var activeIds = new HashSet<string>();

            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                float vehicleReward = 0f;
                var vehicle = emergencyVehicles[i];
                if (vehicle == null || string.IsNullOrEmpty(vehicle.id))
                {
                    rewards.Add(0f);
                    continue;
                }

                if (!TryGetVehicleTargetPosition(vehicle, out var targetPosition))
                {
                    rewards.Add(0f);
                    continue;
                }

                activeIds.Add(vehicle.id);

                float currentDistance = Vector3.Distance(vehicle.position, targetPosition);
                var state = GetOrCreateRewardState(vehicle.id, currentDistance, elapsedTimeSeconds);

                var previousStatus = state.LastStatus;
                var currentStatus = vehicle.gameStatus;

                if (previousStatus == GameDecisionStatus.GameCompleted
                    && currentStatus == GameDecisionStatus.GameCompleted)
                {
                    rewards.Add(0f);
                    continue;
                }

                // Every decision step carries a small time penalty.
                vehicleReward += SimulationConfig.VehicleRewardPerDecisionStepPenalty;

                // +0.5 when getting 1m closer, -0.5 when getting 1m farther.
                float distanceDelta = state.LastDistance - currentDistance;
                vehicleReward += SimulationConfig.VehicleRewardDistancePerMeter * distanceDelta;
                state.LastDistance = currentDistance;

                currentStatus = vehicle.gameStatus;
                if (previousStatus != GameDecisionStatus.GameCompleted
                    && currentStatus == GameDecisionStatus.GameCompleted)
                {
                    float tElapsed = Mathf.Max(elapsedTimeSeconds - state.StartElapsedTime, 0f);
                    float speedRatio = Mathf.Clamp(state.ExpectedTime / Mathf.Max(tElapsed, 0.1f), 0.5f, 1.5f);
                    vehicleReward += SimulationConfig.VehicleRewardArrivalBonusBase * speedRatio;
                    float remainingRatio = Mathf.Clamp01(
                        (SimulationConfig.RuntimeTerminalMaxSeconds - elapsedTimeSeconds)
                        / Mathf.Max(SimulationConfig.RuntimeTerminalMaxSeconds, 0.1f));
                    vehicleReward += SimulationConfig.VehicleRewardEarlyArrivalBonusMax * remainingRatio;

                    Debug.Log($"Vehicle {vehicle.id} reached the destination. Reward: {vehicleReward}");
                }

                state.LastStatus = currentStatus;
                rewards.Add(vehicleReward);
            }

            // Remove stale reward states for vehicles no longer in current emergency list.
            foreach (var id in new List<string>(rewardStateByVehicleId.Keys))
            {
                if (!activeIds.Contains(id))
                {
                    rewardStateByVehicleId.Remove(id);
                }
            }

            return rewards;
        }

        VehicleRewardState GetOrCreateRewardState(string vehicleId, float currentDistance, float elapsedTimeSeconds)
        {
            if (!rewardStateByVehicleId.TryGetValue(vehicleId, out var state))
            {
                float expectedSpeed = Mathf.Max(SimulationConfig.VehicleMaxSpeed, 0.0001f);
                state = new VehicleRewardState
                {
                    ExpectedTime = (currentDistance / expectedSpeed) * 1.2f,
                    StartElapsedTime = elapsedTimeSeconds,
                    LastDistance = currentDistance,
                    LastStatus = GameDecisionStatus.NoDecisionNeeded,
                };
                rewardStateByVehicleId[vehicleId] = state;
            }

            return state;
        }


        // Tools
        bool TryGetVehicleTargetPosition(VehicleEntity vehicle, out Vector3 targetPosition)
        {
            targetPosition = default;

            if (vehicle == null || objectManager == null || string.IsNullOrEmpty(vehicle.targetPointId))
            {
                return false;
            }

            if (objectManager.GetEntity(vehicle.targetPointId) is not TargetPointEntity tp || tp == null)
            {
                return false;
            }

            targetPosition = tp.position;
            return true;
        }
        
    }
}
