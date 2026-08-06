using System;
using System.Collections.Generic;
using CitySimulation.DTO;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Geometry;
using CitySimulation.Global;
using CitySimulation.Runtime.Simulation;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Traffic
{
    public enum TrafficPhaseControlAction
    {
        NoOperation,
        SwitchNow,
        Keep,
        Extend3Seconds
    }

    public readonly struct TrafficObverse
    {
        public TrafficObverse(
            int greenDir0,
            int greenDir1,
            int emergencyCountDir0,
            int emergencyCountDir1,
            int congestionCountInRange,
            int availableExtendLeft,
            float lightTimeLeft,
            GameDecisionStatus gameStatus,
            int objectType)
        {
            GreenDir0 = greenDir0;
            GreenDir1 = greenDir1;
            EmergencyCountDir0 = emergencyCountDir0;
            EmergencyCountDir1 = emergencyCountDir1;
            CongestionCountInRange = congestionCountInRange;
            AvailableExtendLeft = availableExtendLeft;
            LightTimeLeft = lightTimeLeft;
            GameStatus = gameStatus;
            ObjectType = objectType;
        }

        public int GreenDir0 { get; }
        public int GreenDir1 { get; }
        public int EmergencyCountDir0 { get; }
        public int EmergencyCountDir1 { get; }
        public int CongestionCountInRange { get; }
        public int AvailableExtendLeft { get; }
        public float LightTimeLeft { get; }
        public GameDecisionStatus GameStatus { get; }
        public int ObjectType { get; }
    }

    public sealed partial class TrafficService
    {
        internal readonly Dictionary<string, int> trafficExtendCountByLightId = new();
        int episodeTrafficActionNoOperationCount;
        int episodeTrafficActionSwitchNowCount;
        int episodeTrafficActionKeepCount;
        int episodeTrafficActionExtendCount;
        int episodeTrafficAcceptedExtendCount;
        float episodeEmergencyGreenExposureSeconds;
        float episodeEmergencyRedWaitSeconds;
        float pendingSignalControlReward;

        // action
        void TryControlPhaseAtCountdown3(TrafficLightEntity light, float remainingBefore, float remainingAfter)
        {
            if (light == null || string.IsNullOrEmpty(light.id))
            {
                return;
            }

            float triggerCountdown = SimulationConfig.TrafficControlTriggerCountdownSeconds;
            if (!(remainingBefore > triggerCountdown && remainingAfter <= triggerCountdown))
            {
                return;
            }

            int extendCount = 0;
            if (trafficExtendCountByLightId.TryGetValue(light.id, out var value))
            {
                extendCount = value;
            }

            if (extendCount >= SimulationConfig.TrafficPhaseMaxExtendCount)
            {
                return;
            }

            // Only request backend decisions when there is at least one emergency vehicle
            // approaching this intersection; otherwise keep default timer switching.
            if (light.controlledRoadIds == null || light.controlledRoadIds.Count < 2)
            {
                return;
            }

            string road0 = light.controlledRoadIds[0];
            string road1 = light.controlledRoadIds[1];
            int emergency0 = CountEmergencyVehiclesApproachingLightOnRoad(light, road0);
            int emergency1 = CountEmergencyVehiclesApproachingLightOnRoad(light, road1);
            if (emergency0 <= 0 && emergency1 <= 0)
            {
                return;
            }

            light.gameStatus = GameDecisionStatus.NeedDecision;
        }

        public int[] BuildTrafficAvailActionMask(GameDecisionStatus status, int actionSize)
        {
            if (actionSize < 0)
            {
                actionSize = 0;
            }

            var mask = new int[actionSize];
            if (status == GameDecisionStatus.NeedDecision)
            {
                // NeedDecision: NoOperation is not allowed for traffic light.
                // traffic: 1=SwitchNow, 2=Keep, 3=Extend3Seconds
                for (int action = 1; action <= 3 && action < actionSize; action++)
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

        public void ApplyTrafficDecision(IReadOnlyList<TrafficPhaseControlAction> actions)
        {
            if (trafficLights.Count == 0)
            {
                return;
            }

            for (int i = 0; i < trafficLights.Count; i++)
            {
                var light = trafficLights[i];
                if (light == null || string.IsNullOrEmpty(light.id))
                {
                    continue;
                }

                var action = TrafficPhaseControlAction.NoOperation;
                if (actions != null && i < actions.Count)
                {
                    action = actions[i];
                }

                RecordTrafficAction(action);

                if (action == TrafficPhaseControlAction.NoOperation)
                {
                    continue;
                }

                AddSignalActionReward(light, action);
                ApplyTrafficDecisionById(light.id, action);
            }
        }

        public void ApplyTrafficDecision(IReadOnlyList<int> backendActions)
        {
            if (backendActions == null)
            {
                ApplyTrafficDecision((IReadOnlyList<TrafficPhaseControlAction>)null);
                return;
            }

            var mappedActions = new List<TrafficPhaseControlAction>(backendActions.Count);
            for (int i = 0; i < backendActions.Count; i++)
            {
                mappedActions.Add(MapTrafficBackendAction(backendActions[i]));
            }

            ApplyTrafficDecision(mappedActions);
        }

        static TrafficPhaseControlAction MapTrafficBackendAction(int backendAction)
        {
            if (backendAction < 0 || backendAction >= SimulationConfig.UnifiedAgentActionSpaceSize)
            {
                return TrafficPhaseControlAction.NoOperation;
            }

            return backendAction switch
            {
                0 => TrafficPhaseControlAction.NoOperation,
                1 => TrafficPhaseControlAction.SwitchNow,
                2 => TrafficPhaseControlAction.Keep,
                3 => TrafficPhaseControlAction.Extend3Seconds,
                // action id 4 is reserved by unified action-space size=5 and maps to no-op for traffic.
                _ => TrafficPhaseControlAction.NoOperation,
            };
        }
        
        public void ApplyTrafficDecisionById(string lightId, TrafficPhaseControlAction action)
        {
            if (string.IsNullOrEmpty(lightId))
            {
                return;
            }

            if (!TryGetTrafficLightById(lightId, out var light))
            {
                return;
            }

            float phaseDuration = Mathf.Max(0.0001f, SimulationConfig.TrafficGreenDurationSeconds);
            float remaining = phaseDuration - light.timeInPhase;
            if (remaining > SimulationConfig.TrafficControlTriggerCountdownSeconds || remaining <= 0f)
            {
                return;
            }

            if (action == TrafficPhaseControlAction.SwitchNow)
            {
                // Debug.Log($"[TrafficControl] Execute action={action}, lightId={light.id}, remaining={remaining:F2}");
                SwitchPhase(light);
            }

            if (action == TrafficPhaseControlAction.Extend3Seconds)
            {
                int extendCount = 0;
                if (trafficExtendCountByLightId.TryGetValue(light.id, out var value))
                {
                    extendCount = value;
                }

                if (extendCount < SimulationConfig.TrafficPhaseMaxExtendCount)
                {
                    // Debug.Log($"[TrafficControl] Execute action={action}, lightId={light.id}, remaining={remaining:F2}, extendCount={extendCount + 1}/{SimulationConfig.TrafficPhaseMaxExtendCount}");
                    light.timeInPhase = Mathf.Max(0f, light.timeInPhase - SimulationConfig.TrafficPhaseExtendSeconds);
                    trafficExtendCountByLightId[light.id] = extendCount + 1;
                    episodeTrafficAcceptedExtendCount++;
                }
            }

            if (light.gameStatus != GameDecisionStatus.GameCompleted)
            {
                light.gameStatus = GameDecisionStatus.NoDecisionNeeded;
            }
        }

        void SwitchPhase(TrafficLightEntity light)
        {
            if (light == null || light.controlledRoadIds == null || light.controlledRoadIds.Count < 2)
            {
                return;
            }

            light.timeInPhase = 0f;

            string firstRoad = light.controlledRoadIds[0];
            string secondRoad = light.controlledRoadIds[1];

            light.currentGreenRoadId = string.Equals(light.currentGreenRoadId, firstRoad, StringComparison.Ordinal)
                ? secondRoad
                : firstRoad;

            if (!string.IsNullOrEmpty(light.id))
            {
                trafficExtendCountByLightId[light.id] = 0;
            }


        }

        void RecordTrafficAction(TrafficPhaseControlAction action)
        {
            switch (action)
            {
                case TrafficPhaseControlAction.SwitchNow:
                    episodeTrafficActionSwitchNowCount++;
                    break;
                case TrafficPhaseControlAction.Keep:
                    episodeTrafficActionKeepCount++;
                    break;
                case TrafficPhaseControlAction.Extend3Seconds:
                    episodeTrafficActionExtendCount++;
                    break;
                default:
                    episodeTrafficActionNoOperationCount++;
                    break;
            }
        }

        void AddSignalActionReward(TrafficLightEntity light, TrafficPhaseControlAction action)
        {
            if (light == null || light.gameStatus != GameDecisionStatus.NeedDecision)
            {
                return;
            }

            if (action == TrafficPhaseControlAction.SwitchNow)
            {
                pendingSignalControlReward += SimulationConfig.TrafficRewardSwitchPenalty;
                return;
            }

            if (action != TrafficPhaseControlAction.Keep || light.controlledRoadIds == null || light.controlledRoadIds.Count < 2)
            {
                return;
            }

            int greenEmergency = 0;
            int redEmergency = 0;
            for (int i = 0; i < light.controlledRoadIds.Count; i++)
            {
                string roadId = light.controlledRoadIds[i];
                int count = CountEmergencyVehiclesApproachingLightOnRoad(light, roadId);
                if (string.Equals(light.currentGreenRoadId, roadId, StringComparison.Ordinal))
                {
                    greenEmergency += count;
                }
                else
                {
                    redEmergency += count;
                }
            }

            if (redEmergency > greenEmergency)
            {
                pendingSignalControlReward += SimulationConfig.TrafficRewardKeepMismatchPenalty * (redEmergency - greenEmergency);
            }
        }

        public float GetCurrentStepSignalReward(float dt)
        {
            if (dt < 0f)
            {
                dt = 0f;
            }

            float actionReward = pendingSignalControlReward;
            pendingSignalControlReward = 0f;
            float flowReward = 0f;

            if (trafficLights.Count == 0)
            {
                return actionReward;
            }

            // V3奖励函数参数
            const float MAX_QUEUE = 20f;  // 最大排队长度阈值（米）
            const float OVERFLOW_WEIGHT = 0.5f;  // 溢出惩罚权重
            const float BALANCE_WEIGHT = 0.3f;  // 均衡惩罚权重
            const float SWITCH_COST = 0.1f;  // 切换惩罚

            for (int i = 0; i < trafficLights.Count; i++)
            {
                var light = trafficLights[i];
                if (light == null || light.controlledRoadIds == null || light.controlledRoadIds.Count < 2)
                {
                    continue;
                }

                // ============ 计算各方向排队长度 ============
                float[] queueLengths = new float[light.controlledRoadIds.Count];
                float totalQueue = 0f;
                float maxQueue = 0f;
                
                for (int roadIndex = 0; roadIndex < light.controlledRoadIds.Count; roadIndex++)
                {
                    string roadId = light.controlledRoadIds[roadIndex];
                    // 计算该道路上的排队长度（等待车辆数量 × 车辆长度）
                    int waitingCount = CountWaitingVehiclesOnRoad(roadId);
                    float queueLength = waitingCount * 5f;  // 每辆车约5米
                    queueLengths[roadIndex] = queueLength;
                    totalQueue += queueLength;
                    maxQueue = Mathf.Max(maxQueue, queueLength);
                }

                // ============ 负平均排队长度 ============
                float avgQueue = totalQueue / light.controlledRoadIds.Count;
                flowReward -= avgQueue;

                // ============ 溢出惩罚 ============
                if (maxQueue > MAX_QUEUE)
                {
                    flowReward -= (maxQueue - MAX_QUEUE) * OVERFLOW_WEIGHT;
                }

                // ============ 均衡惩罚 ============
                float variance = 0f;
                for (int roadIndex = 0; roadIndex < queueLengths.Length; roadIndex++)
                {
                    variance += Mathf.Pow(queueLengths[roadIndex] - avgQueue, 2);
                }
                variance /= queueLengths.Length;
                flowReward -= Mathf.Sqrt(variance) * BALANCE_WEIGHT;

                // ============ 切换惩罚（如果发生了切换） ============
                if (light.gameStatus == GameDecisionStatus.NeedDecision)
                {
                    // 记录切换次数
                }
            }

            float stepScale = Mathf.Max(dt, 0.0001f) / Mathf.Max(SimulationConfig.RuntimeStepDtSeconds, 0.0001f);
            return actionReward + (flowReward * stepScale / Mathf.Max(1, trafficLights.Count));
        }

        /// <summary>
        /// 计算道路上等待的车辆数量
        /// </summary>
        int CountWaitingVehiclesOnRoad(string roadId)
        {
            if (string.IsNullOrEmpty(roadId))
            {
                return 0;
            }

            var vehicleService = GameServices.VehicleService;
            if (vehicleService == null)
            {
                return 0;
            }

            var vehicles = vehicleService.GetVehicles();
            int count = 0;
            
            foreach (var vehicle in vehicles)
            {
                if (vehicle == null || string.IsNullOrEmpty(vehicle.currentRoadId))
                {
                    continue;
                }

                if (string.Equals(vehicle.currentRoadId, roadId, StringComparison.Ordinal))
                {
                    // 检查车辆是否在等待（速度为0或被前方车辆阻挡）
                    bool isWaiting = vehicle.gameObject == null || 
                                     vehicle.gameStatus == GameDecisionStatus.GameCompleted;
                    
                    // 检查是否被信号灯阻挡
                    if (!isWaiting && CanPassForwardSignal(vehicle.position, vehicle.rotation, roadId))
                    {
                        // 可以通过，不算排队
                        continue;
                    }
                    
                    count++;
                }
            }

            return count;
        }

        public void ResetEpisodeTrafficControlStats()
        {
            episodeTrafficActionNoOperationCount = 0;
            episodeTrafficActionSwitchNowCount = 0;
            episodeTrafficActionKeepCount = 0;
            episodeTrafficActionExtendCount = 0;
            episodeTrafficAcceptedExtendCount = 0;
            episodeEmergencyGreenExposureSeconds = 0f;
            episodeEmergencyRedWaitSeconds = 0f;
            pendingSignalControlReward = 0f;
        }

        public void GetEpisodeTrafficControlStats(
            out int noOperationCount,
            out int switchNowCount,
            out int keepCount,
            out int extendCount,
            out int acceptedExtendCount)
        {
            noOperationCount = episodeTrafficActionNoOperationCount;
            switchNowCount = episodeTrafficActionSwitchNowCount;
            keepCount = episodeTrafficActionKeepCount;
            extendCount = episodeTrafficActionExtendCount;
            acceptedExtendCount = episodeTrafficAcceptedExtendCount;
        }

        public void GetEpisodeEmergencySignalStats(
            int emergencyVehicleCount,
            out float redWaitSecondsTotal,
            out float redWaitSecondsMeanPerVehicle,
            out float greenExposureSecondsTotal,
            out float emergencyGreenTimeRatio)
        {
            redWaitSecondsTotal = episodeEmergencyRedWaitSeconds;
            greenExposureSecondsTotal = episodeEmergencyGreenExposureSeconds;
            redWaitSecondsMeanPerVehicle =
                redWaitSecondsTotal / Mathf.Max(1, emergencyVehicleCount);
            float totalExposure = redWaitSecondsTotal + greenExposureSecondsTotal;
            emergencyGreenTimeRatio =
                totalExposure > 0f ? greenExposureSecondsTotal / totalExposure : 0f;
        }
    
        // observe
        public List<TrafficObverse> BuildTrafficLightObverse()
        {
            var trafficObverseList = new List<TrafficObverse>(trafficLights.Count);

            for (int i = 0; i < trafficLights.Count; i++)
            {
                var light = trafficLights[i];
                if (light == null)
                {
                    continue;
                }

                if (!GetTrafficLightObverseById(light, out var obverse))
                {
                    continue;
                }

                trafficObverseList.Add(obverse);
            }

            return trafficObverseList;
        }

        public bool GetTrafficLightObverseById(TrafficLightEntity light, out TrafficObverse obverse)
        {
            obverse = default;

            if (light == null || light.controlledRoadIds == null || light.controlledRoadIds.Count < 2)
            {
                return false;
            }

            string road0 = light.controlledRoadIds[0];
            string road1 = light.controlledRoadIds[1];
            int greenDir0 = string.Equals(light.currentGreenRoadId, road0, StringComparison.Ordinal) ? 1 : 0;
            int greenDir1 = string.Equals(light.currentGreenRoadId, road1, StringComparison.Ordinal) ? 1 : 0;

            int emergencyCountDir0 = CountEmergencyVehiclesApproachingLightOnRoad(light, road0);
            int emergencyCountDir1 = CountEmergencyVehiclesApproachingLightOnRoad(light, road1);
            int congestionCountInRange = CountCongestionVehiclesInRange(light);

            int usedExtendCount = 0;
            if (!string.IsNullOrEmpty(light.id) && trafficExtendCountByLightId.TryGetValue(light.id, out var value))
            {
                usedExtendCount = Mathf.Max(0, value);
            }
            int availableExtendLeft = Mathf.Max(0, SimulationConfig.TrafficPhaseMaxExtendCount - usedExtendCount);

            float phaseDuration = Mathf.Max(0.0001f, SimulationConfig.TrafficGreenDurationSeconds);
            float lightTimeLeft = Mathf.Max(0f, phaseDuration - light.timeInPhase);

            obverse = new TrafficObverse(
                greenDir0,
                greenDir1,
                emergencyCountDir0,
                emergencyCountDir1,
                congestionCountInRange,
                availableExtendLeft,
                lightTimeLeft,
                light.gameStatus,
                1);
            return true;
        }

        public int CountCongestionVehiclesInRange(TrafficLightEntity targetLight)
        {
            if (targetLight == null)
            {
                return 0;
            }

            var vehicleService = GameServices.VehicleService;
            if (vehicleService == null)
            {
                return 0;
            }

            var vehicles = vehicleService.GetVehicles();
            if (vehicles == null || vehicles.Count == 0)
            {
                return 0;
            }

            int count = 0;
            for (int i = 0; i < vehicles.Count; i++)
            {
                var vehicle = vehicles[i];
                if (vehicle == null)
                {
                    continue;
                }

                if (GeometryUtils.IsNearTarget(
                        vehicle.position,
                        targetLight.position,
                        SimulationConfig.TrafficObserveCongestionMaxRange))
                {
                    count++;
                }
            }

            return count;
        }

        public int CountEmergencyVehiclesApproachingLightOnRoad(TrafficLightEntity targetLight, string roadId)
        {
            if (targetLight == null || string.IsNullOrEmpty(targetLight.id) || string.IsNullOrEmpty(roadId))
            {
                return 0;
            }

            var vehicleService = GameServices.VehicleService;
            if (vehicleService == null)
            {
                return 0;
            }

            var emergencyVehicles = vehicleService.GetEmergencyVehicles();
            if (emergencyVehicles == null || emergencyVehicles.Count == 0)
            {
                return 0;
            }

            int count = 0;
            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null)
                {
                    continue;
                }

                if (!string.Equals(vehicle.currentRoadId, roadId, StringComparison.Ordinal))
                {
                    continue;
                }

                if (!TryGetNearestForwardLight(
                        vehicle.position,
                        vehicle.rotation,
                        roadId,
                        0f,
                        SimulationConfig.TrafficObserveEmergencyVehicleMaxDistance,
                        out var nearest,
                        out _))
                {
                    continue;
                }

                if (nearest != null && string.Equals(nearest.id, targetLight.id, StringComparison.Ordinal))
                {
                    count++;
                }
            }

            return count;
        }


    }
}
