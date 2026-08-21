using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.DTO;
using CitySimulation.Global;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.Runtime.Simulation
{
    public readonly struct VehicleTrackInfo
    {
        public VehicleTrackInfo(
            float x,
            float z,
            int objectType,
            int decision,
            int expertAction,
            string roadId)
        {
            X = x;
            Z = z;
            ObjectType = objectType;
            Decision = decision;
            ExpertAction = expertAction;
            RoadId = roadId;
        }

        public float X { get; }
        public float Z { get; }
        public int ObjectType { get; }
        public int Decision { get; }
        public int ExpertAction { get; }
        public string RoadId { get; }
    }

    /// <summary>
    /// Unity local function interface for future backend integration.
    /// Mirrors init/step/release flow from Simulation_fortoy runtime manager.
    /// for obverse and action . first is vehicle , second is traffic light
    /// </summary>
    public sealed class FunctionInterface
    {
        readonly ObjectManager objectManager;
        bool initialized;
        float elapsedTimeSeconds;
        List<float> currentStepReward_orderbyVehicle;
        float currentStepSignalReward;
        List<int> lastVehicleActions;
        readonly Dictionary<string, float> completionSecondsByVehicleId = new();
        readonly Dictionary<string, int> vehicleDecisionWindowCountById = new();
        readonly Dictionary<string, int> vehicleStraightActionCountById = new();
        readonly Dictionary<string, int> vehicleLeftActionCountById = new();
        readonly Dictionary<string, int> vehicleRightActionCountById = new();
        readonly Dictionary<string, int> vehicleUTurnActionCountById = new();
        readonly Dictionary<string, int> vehicleNonNoopActionCountById = new();
        int episodeVehicleTotal;
        DirectedRoadGraph directedRoadGraph;
        readonly global::CitySimulation.Runtime.Simulation.VehicleObservationDelayBuffer vehicleObservationDelayBuffer = new global::CitySimulation.Runtime.Simulation.VehicleObservationDelayBuffer();

        public FunctionInterface(ObjectManager objectManager = null)
        {
            this.objectManager = objectManager ?? GameServices.ObjectManager;
        }

        public void Init()
        {
            if (initialized)
            {
                return;
            }

            GameServices.RegisterRuntimeServices();

            GameServices.RoadService.Initialize(objectManager);
            GameServices.TrafficService.Initialize(objectManager);
            GameServices.VehicleService.Initialize(objectManager);

            GameServices.RoadService?.Rebuild();
            directedRoadGraph = new DirectedRoadGraph(objectManager, GameServices.TrafficService);

            elapsedTimeSeconds = 0f;
            currentStepReward_orderbyVehicle = new List<float>();
            currentStepSignalReward = 0f;
            lastVehicleActions = new List<int>();
            ResetEpisodeMetrics();

            initialized = true;
        }

        public void Step(float dt = SimulationConfig.RuntimeStepDtSeconds)
        {
            int steps = SimulationConfig.RuntimeStepRepeat;

            if (!initialized)
            {
                Init();
            }

            if (dt <= 0f)
            {
                dt = SimulationConfig.RuntimeStepDtSeconds;
            }

            if (steps <= 0)
            {
                return;
            }

            currentStepReward_orderbyVehicle = new List<float>();
            currentStepSignalReward = 0f;

            for (int i = 0; i < steps; i++)
            {
                elapsedTimeSeconds += dt;
                GameServices.RoadService?.Tick(dt);
                GameServices.TrafficService?.Tick(dt);
                GameServices.VehicleService?.Tick(dt);
                // GameServices.BackendClinet?.Tick(dt); this is for toy

                if (SimulationConfig.RuntimeLowSpeedMode)
                {
                    int sleepMs = Mathf.Max(0, Mathf.RoundToInt(SimulationConfig.RuntimeLowSpeedModePauseSeconds * 1000f));
                    if (sleepMs > 0)
                    {
                        Thread.Sleep(sleepMs);
                    }
                }

                if (GameServices.VehicleService != null)
                {
                    var stepReward = GameServices.VehicleService.GetCurrentStepTotalReward(elapsedTimeSeconds);
                    if (stepReward == null || stepReward.Count == 0)
                    {
                        continue;
                    }

                    if (currentStepReward_orderbyVehicle.Count < stepReward.Count)
                    {
                        for (int j = currentStepReward_orderbyVehicle.Count; j < stepReward.Count; j++)
                        {
                            currentStepReward_orderbyVehicle.Add(0f);
                        }
                    }

                    for (int j = 0; j < stepReward.Count; j++)
                    {
                        currentStepReward_orderbyVehicle[j] += stepReward[j];
                    }

                    UpdateEpisodeMetrics();
                }
                else
                {
                    currentStepReward_orderbyVehicle.Clear();
                    break;
                }

                currentStepSignalReward += GameServices.TrafficService?.GetCurrentStepSignalReward(dt) ?? 0f;
            }
        }

        public void SetRewardStage(int rewardStage)
        {
            if (rewardStage < 1 || rewardStage > 3)
            {
                rewardStage = 3;
            }

            SimulationConfig.RuntimeRewardStage = rewardStage;
        }

        public float GetCurrentStepReward()
        {
            if (!initialized)
            {
                return 0f;
            }

            float vehicleReward = GetCurrentStepVehicleReward();
            float signalReward = currentStepSignalReward;
            switch (SimulationConfig.RuntimeRewardStage)
            {
                case 1:
                    return vehicleReward;
                case 2:
                    return signalReward;
                default:
                    return vehicleReward + signalReward;
            }
        }

        public float GetCurrentStepVehicleReward()
        {
            if (currentStepReward_orderbyVehicle == null || currentStepReward_orderbyVehicle.Count == 0)
            {
                return 0f;
            }

            int n = Mathf.Max(1, SimulationConfig.RuntimeEffectiveVehicleCount);
            int countToSum = Mathf.Min(n, currentStepReward_orderbyVehicle.Count);

            float sum = 0f;
            for (int i = 0; i < countToSum; i++)
            {
                sum += currentStepReward_orderbyVehicle[i];
            }

            if (IsTimeLimitTerminal())
            {
                sum += GetTimeoutPenaltyForEffectiveVehicles(countToSum);
            }

            float reward = sum / Mathf.Max(1, countToSum);
            return reward;
        }

        public float GetCurrentStepSignalReward()
        {
            return currentStepSignalReward;
        }

        public bool IsTerminal()
        {
            if (!initialized)
            {
                return false;
            }

            if (IsTimeLimitTerminal())
            {
                return true;
            }

            return IsSuccessTerminal();
        }

        public bool IsTimeLimitTerminal()
        {
            if (!initialized)
            {
                return false;
            }

            return elapsedTimeSeconds > SimulationConfig.RuntimeTerminalMaxSeconds;
        }

        public bool IsSuccessTerminal()
        {
            if (!initialized)
            {
                return false;
            }

            var vehicleService = GameServices.VehicleService;
            if (vehicleService == null)
            {
                return false;
            }

            var emergencyVehicles = vehicleService.GetEmergencyVehicles();
            if (emergencyVehicles == null || emergencyVehicles.Count == 0)
            {
                return false;
            }

            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null)
                {
                    continue;
                }

                if (vehicle.gameStatus != GameDecisionStatus.GameCompleted)
                {
                    return false;
                }
            }

            Debug.Log($"[time = {elapsedTimeSeconds}");
            return true;
        }

        public int GetObsSize()
        {
            return SimulationConfig.UnifiedAgentObsSize;
        }
        
        public List<float[]> GetObs()
        {
            if (!initialized)
            {
                Init();
            }

            int obsSize = GetObsSize();
            var result = new List<float[]>();
            var trafficService = GameServices.TrafficService;

            if (trafficService != null)
            {
                var trafficLights = trafficService.TrafficLights;
                for (int i = 0; trafficLights != null && i < trafficLights.Count; i++)
                {
                    var light = trafficLights[i];
                    if (light == null || !trafficService.GetTrafficLightObverseById(light, out var obverse))
                    {
                        continue;
                    }

                    TryGetNearestControlledEmergencyVehicle(light, out var nearestVehicle, out var nearestVehicleObverse);
                    float vehicleFromDir = NormalizeVehicleFromDir(light, nearestVehicle);
                    float sinThetaToTarget = nearestVehicleObverse.HasValue ? nearestVehicleObverse.Value.SinThetaToTarget : 0f;
                    float cosThetaToTarget = nearestVehicleObverse.HasValue ? nearestVehicleObverse.Value.CosThetaToTarget : 0f;
                    EstimateGraphRouteFeatures(
                        nearestVehicle,
                        light,
                        out float graphDistanceToTarget,
                        out float straightTargetDelta,
                        out float leftTargetDelta,
                        out float rightTargetDelta,
                        out float uturnTargetDelta);
                    if (nearestVehicle != null)
                    {
                        var currentSnapshot = new VehicleObservationSnapshot
                        {
                            PositionX = nearestVehicle.position.x,
                            PositionZ = nearestVehicle.position.z,
                            SinThetaToTarget = sinThetaToTarget,
                            CosThetaToTarget = cosThetaToTarget,
                            DistanceToTarget = graphDistanceToTarget,
                            VehicleFromDir = vehicleFromDir,
                            StraightTargetDelta = straightTargetDelta,
                            LeftTargetDelta = leftTargetDelta,
                            RightTargetDelta = rightTargetDelta,
                            UTurnTargetDelta = uturnTargetDelta,
                        };
                        float communicationDistance = Vector3.Distance(nearestVehicle.position, light.position);
                        string observationLinkKey = $"{light.id}:{nearestVehicle.id}";
                        var transmittedSnapshot = vehicleObservationDelayBuffer.GetSnapshotForSend(
                            observationLinkKey,
                            currentSnapshot,
                            SimulationConfig.RuntimeObservationDelayEffective,
                            SimulationConfig.RuntimeObservationMaxPacketLossProbability,
                            communicationDistance,
                            SimulationConfig.TrafficObserveEmergencyVehicleMaxDistance);
                        sinThetaToTarget = transmittedSnapshot.SinThetaToTarget;
                        cosThetaToTarget = transmittedSnapshot.CosThetaToTarget;
                        graphDistanceToTarget = transmittedSnapshot.DistanceToTarget;
                        vehicleFromDir = transmittedSnapshot.VehicleFromDir;
                        straightTargetDelta = transmittedSnapshot.StraightTargetDelta;
                        leftTargetDelta = transmittedSnapshot.LeftTargetDelta;
                        rightTargetDelta = transmittedSnapshot.RightTargetDelta;
                        uturnTargetDelta = transmittedSnapshot.UTurnTargetDelta;
                    }

                    var raw = new[]
                    {
                        (float)obverse.GreenDir0,
                        (float)obverse.GreenDir1,
                        (float)obverse.EmergencyCountDir0,
                        (float)obverse.EmergencyCountDir1,
                        (float)obverse.CongestionCountInRange,
                        (float)obverse.AvailableExtendLeft,
                        NormalizePhaseTime(obverse.LightTimeLeft),
                        nearestVehicle != null && nearestVehicle.gameStatus == GameDecisionStatus.NeedDecision ? 1f : 0f,
                        graphDistanceToTarget,
                        vehicleFromDir,
                        sinThetaToTarget,
                        cosThetaToTarget,
                        straightTargetDelta,
                        leftTargetDelta,
                        rightTargetDelta,
                        uturnTargetDelta
                    };
                    result.Add(PadObs(raw, obsSize));
                }
            }

            return result;
        }

        static float ResolveNearestForwardLightDistance(TrafficService trafficService, IReadOnlyList<VehicleEntity> emergencyVehicles, int index)
        {
            if (trafficService == null
                || emergencyVehicles == null
                || index < 0
                || index >= emergencyVehicles.Count)
            {
                return float.PositiveInfinity;
            }

            var vehicle = emergencyVehicles[index];
            if (vehicle == null || string.IsNullOrEmpty(vehicle.currentRoadId))
            {
                return float.PositiveInfinity;
            }

            bool found = trafficService.TryGetNearestForwardLight(
                vehicle.position,
                vehicle.rotation,
                vehicle.currentRoadId,
                0f,
                SimulationConfig.TrafficObserveEmergencyVehicleMaxDistance,
                out _,
                out float nearestDistance);

            return found ? nearestDistance : float.PositiveInfinity;
        }

        public int GetTotalActionsSize()
        {
            return SimulationConfig.UnifiedAgentActionSpaceSize;
        }

        public List<int[]> GetAvailActions()
        {
            if (!initialized)
            {
                Init();
            }

            int actionSize = GetTotalActionsSize();
            var result = new List<int[]>();

            var trafficService = GameServices.TrafficService;
            if (trafficService != null)
            {
                var trafficLights = trafficService.TrafficLights;
                for (int i = 0; i < trafficLights.Count; i++)
                {
                    var light = trafficLights[i];
                    if (light == null)
                    {
                        continue;
                    }

                    if (!trafficService.GetTrafficLightObverseById(light, out _))
                    {
                        continue;
                    }

                    result.Add(BuildIntersectionAvailActionMask(light, actionSize));
                }
            }

            return result;
        }

        public void ApplyDecision(int[] backendActions)
        {
            ApplyDecision((IReadOnlyList<int>)backendActions);
        }

        public void ApplyDecision(IReadOnlyList<int> backendActions)
        {
            if (!initialized)
            {
                Init();
            }

            var vehicleService = GameServices.VehicleService;
            var trafficService = GameServices.TrafficService;

            int trafficCount = trafficService?.TrafficLights?.Count ?? 0;

            var diagnosticVehicleActions = new List<int>(vehicleService?.GetEmergencyVehicles()?.Count ?? 0);
            for (int i = 0; i < diagnosticVehicleActions.Capacity; i++)
            {
                diagnosticVehicleActions.Add(0);
            }
            var vehicleIdsToApply = new List<string>();
            var vehicleActionsToApply = new List<VehicleDecisionAction>();
            var trafficActions = new List<TrafficPhaseControlAction>(trafficCount);
            for (int i = 0; i < trafficCount; i++)
            {
                trafficActions.Add(TrafficPhaseControlAction.NoOperation);
            }

            int agentIndex = 0;
            for (int i = 0; i < trafficCount; i++)
            {
                var light = trafficService.TrafficLights[i];
                if (light == null || !trafficService.GetTrafficLightObverseById(light, out _))
                {
                    continue;
                }

                int actionOffset = agentIndex * 2;
                agentIndex++;
                int vehicleAction = (backendActions != null && actionOffset < backendActions.Count) ? backendActions[actionOffset] : 0;
                int signalAction = (backendActions != null && actionOffset + 1 < backendActions.Count) ? backendActions[actionOffset + 1] : 0;

                if (TryGetNearestControlledEmergencyVehicle(light, out var vehicle, out _)
                    && vehicle != null
                    && vehicle.gameStatus == GameDecisionStatus.NeedDecision)
                {
                    var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
                    if (emergencyVehicles != null)
                    {
                        for (int vehicleIndex = 0; vehicleIndex < emergencyVehicles.Count; vehicleIndex++)
                        {
                            if (emergencyVehicles[vehicleIndex] != null && emergencyVehicles[vehicleIndex].id == vehicle.id)
                            {
                                diagnosticVehicleActions[vehicleIndex] = vehicleAction;
                                break;
                            }
                        }
                    }

                    vehicleIdsToApply.Add(vehicle.id);
                    vehicleActionsToApply.Add(MapVehicleBackendAction(vehicleAction));
                }

                if (light != null && light.gameStatus == GameDecisionStatus.NeedDecision)
                {
                    trafficActions[i] = signalAction == 1
                        ? TrafficPhaseControlAction.SwitchNow
                        : TrafficPhaseControlAction.Keep;
                }
            }

            lastVehicleActions = new List<int>(diagnosticVehicleActions);
            RecordVehicleDecisionDiagnostics(diagnosticVehicleActions);
            for (int i = 0; i < vehicleIdsToApply.Count; i++)
            {
                vehicleService?.ApplyVehicleDecisionById(vehicleIdsToApply[i], vehicleActionsToApply[i]);
            }
            trafficService?.ApplyTrafficDecision(trafficActions);
        }
       

        public void Release()
        {
            if (!initialized)
            {
                return;
            }

            GameServices.ReleaseRuntimeServices();
            elapsedTimeSeconds = 0f;
            currentStepReward_orderbyVehicle?.Clear();
            currentStepSignalReward = 0f;
            lastVehicleActions?.Clear();
            vehicleObservationDelayBuffer.Clear();
            directedRoadGraph = null;
            ResetEpisodeMetrics();
            initialized = false;
        }

        public void Reset(string mapId)
        {
            Reset(mapId, randomizeTargetPoints: false, targetSeed: 0);
        }

        public void Reset(bool randomizeTargetPoints, int targetSeed)
        {
            if (TryGetLoadMapNameFromUI(out var uiMapId) && !string.IsNullOrEmpty(uiMapId))
            {
                Reset(uiMapId, randomizeTargetPoints, targetSeed);
                return;
            }

            Reset("xiongan_30", randomizeTargetPoints, targetSeed);
        }

        public void Reset(string mapId, bool randomizeTargetPoints, int targetSeed)
        {
            // 1) Unload runtime services to release runtime-held states/locks.
            GameServices.ReleaseRuntimeServices();
            initialized = false;
            currentStepReward_orderbyVehicle?.Clear();
            currentStepSignalReward = 0f;
            lastVehicleActions?.Clear();
            vehicleObservationDelayBuffer.Clear();
            ResetEpisodeMetrics();

            // 2) Remove all current entities/GameObjects from ObjectManager.
            objectManager.ImportAll(new ObjectManager.MapSnapshot());

            // 3) Reload the formal 30-intersection map unless explicitly overridden.
            var targetMapId = string.IsNullOrEmpty(mapId) ? "xiongan_30" : mapId;
            GameServices.MapManager.SetCurrentMapId(targetMapId);
            GameServices.MapManager.LoadMap();
            if (randomizeTargetPoints)
            {
                RandomizeTargetPointsOnRoad(targetSeed);
            }

            // 4) Recreate runtime services and caches.
            Init();
        }

        public void Reset()
        {
            if (TryGetLoadMapNameFromUI(out var uiMapId) && !string.IsNullOrEmpty(uiMapId))
            {
                Reset(uiMapId);
                return;
            }

            Reset("xiongan_30");
        }

        void RandomizeTargetPointsOnRoad(int seed)
        {
            if (objectManager == null)
            {
                return;
            }

            var targetPoints = objectManager.GetAllEntities().OfType<TargetPointEntity>().ToList();
            var roads = objectManager.GetAllEntities().OfType<RoadEntity>().ToList();
            if (targetPoints.Count == 0 || roads.Count == 0)
            {
                return;
            }

            var roadPoints = new List<Vector3>();
            for (int i = 0; i < roads.Count; i++)
            {
                var road = roads[i];
                if (road == null)
                {
                    continue;
                }

                if (road.controlPoints != null && road.controlPoints.Count > 0)
                {
                    roadPoints.AddRange(road.controlPoints);
                }
                else
                {
                    roadPoints.Add(road.position);
                }
            }

            if (roadPoints.Count == 0)
            {
                return;
            }

            float minX = roadPoints.Min(p => p.x);
            float maxX = roadPoints.Max(p => p.x);
            float minZ = roadPoints.Min(p => p.z);
            float maxZ = roadPoints.Max(p => p.z);
            float centerX = (minX + maxX) * 0.5f;
            float centerZ = (minZ + maxZ) * 0.5f;
            float halfX = Mathf.Max(0.001f, (maxX - minX) * 0.35f);
            float halfZ = Mathf.Max(0.001f, (maxZ - minZ) * 0.35f);

            var random = new System.Random(seed);
            for (int i = 0; i < targetPoints.Count; i++)
            {
                var target = targetPoints[i];
                if (target == null)
                {
                    continue;
                }

                float sampleX = centerX + ((float)random.NextDouble() * 2f - 1f) * halfX;
                float sampleZ = centerZ + ((float)random.NextDouble() * 2f - 1f) * halfZ;
                var sample = new Vector3(sampleX, target.position.y, sampleZ);
                var snapped = FindNearestRoadCenterPoint(sample, roads);
                snapped.y = target.position.y;
                target.ApplyTransform(snapped, target.rotation);
            }
        }

        static Vector3 FindNearestRoadCenterPoint(Vector3 sample, IReadOnlyList<RoadEntity> roads)
        {
            Vector3 best = sample;
            float bestDistSq = float.PositiveInfinity;

            for (int i = 0; i < roads.Count; i++)
            {
                var road = roads[i];
                if (road == null)
                {
                    continue;
                }

                var points = road.controlPoints;
                if (points == null || points.Count == 0)
                {
                    UpdateNearestPoint(road.position, sample, ref best, ref bestDistSq);
                    continue;
                }

                if (points.Count == 1)
                {
                    UpdateNearestPoint(points[0], sample, ref best, ref bestDistSq);
                    continue;
                }

                for (int j = 0; j < points.Count - 1; j++)
                {
                    var projected = ProjectPointToSegmentXZ(sample, points[j], points[j + 1]);
                    UpdateNearestPoint(projected, sample, ref best, ref bestDistSq);
                }
            }

            return best;
        }

        static void UpdateNearestPoint(Vector3 candidate, Vector3 sample, ref Vector3 best, ref float bestDistSq)
        {
            float dx = candidate.x - sample.x;
            float dz = candidate.z - sample.z;
            float distSq = dx * dx + dz * dz;
            if (distSq >= bestDistSq)
            {
                return;
            }

            bestDistSq = distSq;
            best = candidate;
        }

        static Vector3 ProjectPointToSegmentXZ(Vector3 point, Vector3 a, Vector3 b)
        {
            Vector2 p = new Vector2(point.x, point.z);
            Vector2 av = new Vector2(a.x, a.z);
            Vector2 bv = new Vector2(b.x, b.z);
            Vector2 ab = bv - av;
            float denom = ab.sqrMagnitude;
            if (denom <= 0.000001f)
            {
                return a;
            }

            float t = Mathf.Clamp01(Vector2.Dot(p - av, ab) / denom);
            Vector2 projected = av + ab * t;
            return new Vector3(projected.x, Mathf.Lerp(a.y, b.y, t), projected.y);
        }

        public List<VehicleTrackInfo> GetVehicleTrackInfos()
        {
            var tracks = new List<VehicleTrackInfo>();
            if (!initialized)
            {
                return tracks;
            }

            var vehicleService = GameServices.VehicleService;
            var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
            var vehicleObverseList = vehicleService?.GetEmergencyVehicleObverse();
            if (emergencyVehicles == null || emergencyVehicles.Count == 0)
            {
                return tracks;
            }

            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null)
                {
                    continue;
                }

                int decision = 0;
                if (lastVehicleActions != null && i < lastVehicleActions.Count)
                {
                    decision = lastVehicleActions[i];
                }

                int expertAction = 0;
                if (vehicleObverseList != null && i < vehicleObverseList.Count)
                {
                    var obverse = vehicleObverseList[i];
                    bool needDecision = vehicle.gameStatus == GameDecisionStatus.NeedDecision;
                    expertAction = VehicleExpertActionHeuristic.InferAction(
                        obverse.SinThetaToTarget,
                        obverse.CosThetaToTarget,
                        needDecision);
                }

                tracks.Add(new VehicleTrackInfo(
                    vehicle.position.x,
                    vehicle.position.z,
                    0,
                    decision,
                    expertAction,
                    vehicle.currentRoadId));
            }

            return tracks;
        }

        public void GetEpisodeVehicleCompletionStats(out float allAvgSeconds, out float completionRate)
        {
            GetEpisodeVehicleCompletionStats(
                out allAvgSeconds,
                out completionRate,
                out _,
                out _,
                out _,
                out _,
                out _);
        }

        public void GetEpisodeVehicleCompletionStats(
            out float allAvgSeconds,
            out float completionRate,
            out int completedCount,
            out int totalCount,
            out int unfinishedCount,
            out float unfinishedAvgDistance,
            out float unfinishedMaxDistance)
        {
            allAvgSeconds = 0f;
            completedCount = completionSecondsByVehicleId.Count;
            totalCount = Mathf.Max(episodeVehicleTotal, completedCount);
            unfinishedCount = Mathf.Max(0, totalCount - completedCount);
            unfinishedAvgDistance = 0f;
            unfinishedMaxDistance = 0f;
            completionRate = totalCount > 0 ? (float)completedCount / totalCount : 0f;

            if (totalCount <= 0)
            {
                return;
            }

            float sum = 0f;
            foreach (var kv in completionSecondsByVehicleId)
            {
                sum += kv.Value;
            }

            float truncatedUncompletedSeconds = Mathf.Min(elapsedTimeSeconds, SimulationConfig.RuntimeTerminalMaxSeconds);
            sum += unfinishedCount * truncatedUncompletedSeconds;

            allAvgSeconds = sum / totalCount;
            GetUnfinishedVehicleDistanceStats(out unfinishedAvgDistance, out unfinishedMaxDistance);
        }

        public void GetEpisodeArrivalTimeStats(
            out float completedArrivalTimeMean,
            out float completedArrivalTimeStd,
            out float completedArrivalTimeP95,
            out float completedArrivalTimeMax)
        {
            completedArrivalTimeMean = 0f;
            completedArrivalTimeStd = 0f;
            completedArrivalTimeP95 = 0f;
            completedArrivalTimeMax = 0f;
            if (completionSecondsByVehicleId.Count == 0)
            {
                return;
            }

            var values = completionSecondsByVehicleId.Values.OrderBy(value => value).ToArray();
            completedArrivalTimeMean = values.Average();
            float squaredDeviationSum = 0f;
            for (int i = 0; i < values.Length; i++)
            {
                float deviation = values[i] - completedArrivalTimeMean;
                squaredDeviationSum += deviation * deviation;
            }
            completedArrivalTimeStd = Mathf.Sqrt(squaredDeviationSum / values.Length);
            int p95Index = Mathf.Clamp(Mathf.CeilToInt(values.Length * 0.95f) - 1, 0, values.Length - 1);
            completedArrivalTimeP95 = values[p95Index];
            completedArrivalTimeMax = values[values.Length - 1];
        }

        public void GetEpisodeObservationDelayStats(
            out int sendCount,
            out int staleCount,
            out float staleRatio,
            out float packetLossProbabilityMean,
            out float packetLossProbabilityP95,
            out float observationAgeStepsMean,
            out float observationAgeStepsP95,
            out float observationAgeSecondsMean,
            out float observationAgeSecondsP95)
        {
            vehicleObservationDelayBuffer.GetEpisodeStats(
                out sendCount,
                out staleCount,
                out staleRatio,
                out packetLossProbabilityMean,
                out packetLossProbabilityP95,
                out observationAgeStepsMean,
                out observationAgeStepsP95,
                out observationAgeSecondsMean,
                out observationAgeSecondsP95);
        }

        void ResetEpisodeMetrics()
        {
            completionSecondsByVehicleId.Clear();
            vehicleDecisionWindowCountById.Clear();
            vehicleStraightActionCountById.Clear();
            vehicleLeftActionCountById.Clear();
            vehicleRightActionCountById.Clear();
            vehicleUTurnActionCountById.Clear();
            vehicleNonNoopActionCountById.Clear();
            episodeVehicleTotal = 0;
            GameServices.TrafficService?.ResetEpisodeTrafficControlStats();
        }

        void RecordVehicleDecisionDiagnostics(IReadOnlyList<int> vehicleActions)
        {
            var vehicleService = GameServices.VehicleService;
            var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
            if (emergencyVehicles == null || emergencyVehicles.Count == 0)
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

                if (vehicle.gameStatus != GameDecisionStatus.NeedDecision)
                {
                    continue;
                }

                IncrementCount(vehicleDecisionWindowCountById, vehicle.id);

                int action = vehicleActions != null && i < vehicleActions.Count ? vehicleActions[i] : 0;
                if (action == 0)
                {
                    continue;
                }

                IncrementCount(vehicleNonNoopActionCountById, vehicle.id);
                switch (action)
                {
                    case 1:
                        IncrementCount(vehicleStraightActionCountById, vehicle.id);
                        break;
                    case 2:
                        IncrementCount(vehicleLeftActionCountById, vehicle.id);
                        break;
                    case 3:
                        IncrementCount(vehicleRightActionCountById, vehicle.id);
                        break;
                    case 4:
                        IncrementCount(vehicleUTurnActionCountById, vehicle.id);
                        break;
                }
            }
        }

        static void IncrementCount(Dictionary<string, int> counts, string key)
        {
            if (counts == null || string.IsNullOrEmpty(key))
            {
                return;
            }

            counts.TryGetValue(key, out int current);
            counts[key] = current + 1;
        }

        public void GetPerVehicleDiagnostics(
            out string[] vehicleIds,
            out float[] vehicleFinalDistances,
            out int[] vehicleCompletedFlags,
            out int[] vehicleDecisionWindowCounts,
            out int[] vehicleNonNoopActionCounts,
            out int[] vehicleStraightActionCounts,
            out int[] vehicleLeftActionCounts,
            out int[] vehicleRightActionCounts,
            out int[] vehicleUTurnActionCounts)
        {
            var vehicleService = GameServices.VehicleService;
            var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
            int count = emergencyVehicles?.Count ?? 0;

            vehicleIds = new string[count];
            vehicleFinalDistances = new float[count];
            vehicleCompletedFlags = new int[count];
            vehicleDecisionWindowCounts = new int[count];
            vehicleNonNoopActionCounts = new int[count];
            vehicleStraightActionCounts = new int[count];
            vehicleLeftActionCounts = new int[count];
            vehicleRightActionCounts = new int[count];
            vehicleUTurnActionCounts = new int[count];

            for (int i = 0; i < count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null)
                {
                    vehicleIds[i] = string.Empty;
                    vehicleFinalDistances[i] = 0f;
                    continue;
                }

                string id = vehicle.id ?? string.Empty;
                vehicleIds[i] = id;
                vehicleCompletedFlags[i] = vehicle.gameStatus == GameDecisionStatus.GameCompleted ? 1 : 0;
                vehicleFinalDistances[i] = vehicleCompletedFlags[i] == 1
                    ? 0f
                    : (TryGetVehicleTargetDistance(vehicle, out float distance) ? distance : -1f);

                vehicleDecisionWindowCounts[i] = GetCount(vehicleDecisionWindowCountById, id);
                vehicleNonNoopActionCounts[i] = GetCount(vehicleNonNoopActionCountById, id);
                vehicleStraightActionCounts[i] = GetCount(vehicleStraightActionCountById, id);
                vehicleLeftActionCounts[i] = GetCount(vehicleLeftActionCountById, id);
                vehicleRightActionCounts[i] = GetCount(vehicleRightActionCountById, id);
                vehicleUTurnActionCounts[i] = GetCount(vehicleUTurnActionCountById, id);
            }
        }

        static int GetCount(Dictionary<string, int> counts, string key)
        {
            if (counts == null || string.IsNullOrEmpty(key))
            {
                return 0;
            }

            return counts.TryGetValue(key, out int value) ? value : 0;
        }

        void UpdateEpisodeMetrics()
        {
            var vehicleService = GameServices.VehicleService;
            var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
            if (emergencyVehicles == null)
            {
                episodeVehicleTotal = 0;
                return;
            }

            episodeVehicleTotal = emergencyVehicles.Count;
            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null || string.IsNullOrEmpty(vehicle.id))
                {
                    continue;
                }

                if (vehicle.gameStatus == GameDecisionStatus.GameCompleted && !completionSecondsByVehicleId.ContainsKey(vehicle.id))
                {
                    completionSecondsByVehicleId[vehicle.id] = elapsedTimeSeconds;
                }
            }
        }

        float GetTimeoutPenaltyForEffectiveVehicles(int countToSum)
        {
            var vehicleService = GameServices.VehicleService;
            var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
            if (emergencyVehicles == null || emergencyVehicles.Count == 0 || countToSum <= 0)
            {
                return 0f;
            }

            float penalty = 0f;
            int count = Mathf.Min(countToSum, emergencyVehicles.Count);
            for (int i = 0; i < count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null || vehicle.gameStatus == GameDecisionStatus.GameCompleted)
                {
                    continue;
                }

                float distance = TryGetVehicleTargetDistance(vehicle, out var d) ? d : 0f;
                float onePenalty = SimulationConfig.VehicleRewardTimeoutPenaltyBase
                    + SimulationConfig.VehicleRewardTimeoutRemainingDistancePerMeter * Mathf.Max(0f, distance);
                penalty += Mathf.Max(SimulationConfig.VehicleRewardTimeoutPenaltyMin, onePenalty);
            }

            return penalty;
        }

        void GetUnfinishedVehicleDistanceStats(out float avgDistance, out float maxDistance)
        {
            avgDistance = 0f;
            maxDistance = 0f;

            var vehicleService = GameServices.VehicleService;
            var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
            if (emergencyVehicles == null || emergencyVehicles.Count == 0)
            {
                return;
            }

            float sum = 0f;
            int count = 0;
            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null || vehicle.gameStatus == GameDecisionStatus.GameCompleted)
                {
                    continue;
                }

                if (!TryGetVehicleTargetDistance(vehicle, out float distance))
                {
                    continue;
                }

                sum += distance;
                maxDistance = Mathf.Max(maxDistance, distance);
                count++;
            }

            if (count > 0)
            {
                avgDistance = sum / count;
            }
        }

        bool TryGetVehicleTargetDistance(VehicleEntity vehicle, out float distance)
        {
            distance = 0f;
            if (vehicle == null || objectManager == null || string.IsNullOrEmpty(vehicle.targetPointId))
            {
                return false;
            }

            if (objectManager.GetEntity(vehicle.targetPointId) is not TargetPointEntity targetPoint || targetPoint == null)
            {
                return false;
            }

            distance = Vector3.Distance(vehicle.position, targetPoint.position);
            return true;
        }

        bool TryGetVehicleTargetPosition(VehicleEntity vehicle, out Vector3 targetPosition)
        {
            targetPosition = default;
            if (vehicle == null || objectManager == null || string.IsNullOrEmpty(vehicle.targetPointId))
            {
                return false;
            }

            if (objectManager.GetEntity(vehicle.targetPointId) is not TargetPointEntity targetPoint || targetPoint == null)
            {
                return false;
            }

            targetPosition = targetPoint.position;
            return true;
        }

        // ===================
        // Tools
        // ===================
        static float[] PadObs(float[] source, int targetSize)
        {
            if (source == null)
            {
                return new float[targetSize];
            }

            if (source.Length == targetSize)
            {
                return source;
            }

            var output = new float[targetSize];
            int copyCount = Math.Min(source.Length, targetSize);
            Array.Copy(source, output, copyCount);
            return output;
        }

        static float NormalizeMapCoordinate(float value)
        {
            float halfExtent = Mathf.Max(0.0001f, SimulationConfig.RuntimeObservationMapExtentMeters * 0.5f);
            return Mathf.Clamp(value / halfExtent, -1f, 1f);
        }

        static float NormalizeDistance(float value)
        {
            float scale = Mathf.Max(0.0001f, SimulationConfig.RuntimeObservationDistanceScaleMeters);
            return Mathf.Clamp(value / scale, 0f, 1f);
        }

        static float NormalizePhaseTime(float value)
        {
            float scale = Mathf.Max(0.0001f, SimulationConfig.TrafficGreenDurationSeconds);
            return Mathf.Clamp(value / scale, 0f, 1f);
        }

        float NormalizeVehicleFromDir(TrafficLightEntity light, VehicleEntity vehicle)
        {
            if (light == null
                || vehicle == null
                || light.controlledRoadIds == null
                || string.IsNullOrEmpty(vehicle.currentRoadId))
            {
                return -1f;
            }

            for (int i = 0; i < light.controlledRoadIds.Count; i++)
            {
                if (string.Equals(light.controlledRoadIds[i], vehicle.currentRoadId, StringComparison.Ordinal))
                {
                    return light.controlledRoadIds.Count <= 1
                        ? 0f
                        : Mathf.Clamp01((float)i / (light.controlledRoadIds.Count - 1));
                }
            }

            return -1f;
        }

        void EstimateGraphRouteFeatures(
            VehicleEntity vehicle,
            TrafficLightEntity light,
            out float graphDistanceToTarget,
            out float straightTargetDelta,
            out float leftTargetDelta,
            out float rightTargetDelta,
            out float uturnTargetDelta)
        {
            graphDistanceToTarget = 0f;
            straightTargetDelta = -1f;
            leftTargetDelta = -1f;
            rightTargetDelta = -1f;
            uturnTargetDelta = -1f;

            if (vehicle == null
                || light == null
                || directedRoadGraph == null
                || !TryGetVehicleTargetPosition(vehicle, out var targetPosition)
                || !directedRoadGraph.TryGetRouteFeatures(
                    vehicle,
                    light,
                    targetPosition,
                    out float currentDistance,
                    out float straightDistance,
                    out float leftDistance,
                    out float rightDistance,
                    out float uturnDistance))
            {
                return;
            }

            graphDistanceToTarget = NormalizeDistance(currentDistance);
            straightTargetDelta = NormalizeGraphDistanceDelta(currentDistance, straightDistance);
            leftTargetDelta = NormalizeGraphDistanceDelta(currentDistance, leftDistance);
            rightTargetDelta = NormalizeGraphDistanceDelta(currentDistance, rightDistance);
            uturnTargetDelta = NormalizeGraphDistanceDelta(currentDistance, uturnDistance);
        }

        static float NormalizeGraphDistanceDelta(float currentDistance, float actionDistance)
        {
            if (float.IsNaN(actionDistance) || float.IsPositiveInfinity(actionDistance))
            {
                return -1f;
            }

            float scale = Mathf.Max(0.0001f, SimulationConfig.IntersectionGraphDistanceDeltaScaleMeters);
            return Mathf.Clamp((currentDistance - actionDistance) / scale, -1f, 1f);
        }

        int[] BuildIntersectionAvailActionMask(TrafficLightEntity light, int actionSize)
        {
            var mask = new int[actionSize];
            if (mask.Length == 0)
            {
                return mask;
            }

            bool hasVehicleDecision = TryGetNearestControlledEmergencyVehicle(light, out var vehicle, out _)
                && vehicle != null
                && vehicle.gameStatus == GameDecisionStatus.NeedDecision;

            if (hasVehicleDecision)
            {
                var trafficService = GameServices.TrafficService;
                for (int action = 1; action < SimulationConfig.IntersectionVehicleActionSpaceSize && action < mask.Length; action++)
                {
                    if (action == 4
                        && (trafficService == null
                            || !trafficService.CanExecuteAtomicUTurn(light, vehicle.currentRoadId)))
                    {
                        continue;
                    }
                    mask[action] = 1;
                }
            }
            else
            {
                mask[0] = 1;
            }

            int signalOffset = SimulationConfig.IntersectionVehicleActionSpaceSize;
            if (signalOffset < mask.Length)
            {
                if (light != null && light.gameStatus == GameDecisionStatus.NeedDecision)
                {
                    mask[signalOffset] = 1;
                    if (signalOffset + 1 < mask.Length)
                    {
                        mask[signalOffset + 1] = 1;
                    }
                }
                else
                {
                    mask[signalOffset] = 1;
                }
            }

            return mask;
        }

        bool TryGetNearestControlledEmergencyVehicle(
            TrafficLightEntity light,
            out VehicleEntity nearestVehicle,
            out VehicleObverse? nearestObverse)
        {
            nearestVehicle = null;
            nearestObverse = null;

            var vehicleService = GameServices.VehicleService;
            var trafficService = GameServices.TrafficService;
            var emergencyVehicles = vehicleService?.GetEmergencyVehicles();
            var obverses = vehicleService?.GetEmergencyVehicleObverse();
            if (light == null || vehicleService == null || trafficService == null || emergencyVehicles == null)
            {
                return false;
            }

            float bestDistance = float.PositiveInfinity;
            for (int i = 0; i < emergencyVehicles.Count; i++)
            {
                var vehicle = emergencyVehicles[i];
                if (vehicle == null || string.IsNullOrEmpty(vehicle.currentRoadId))
                {
                    continue;
                }

                bool found = trafficService.TryGetNearestForwardLight(
                    vehicle.position,
                    vehicle.rotation,
                    vehicle.currentRoadId,
                    0f,
                    SimulationConfig.BackendControlRadius,
                    out var forwardLight,
                    out float distance);

                if (!found || forwardLight == null || forwardLight.id != light.id || distance >= bestDistance)
                {
                    continue;
                }

                bestDistance = distance;
                nearestVehicle = vehicle;
                if (obverses != null && i < obverses.Count)
                {
                    nearestObverse = obverses[i];
                }
            }

            return nearestVehicle != null;
        }

        static VehicleDecisionAction MapVehicleBackendAction(int backendAction)
        {
            return backendAction switch
            {
                1 => VehicleDecisionAction.Straight,
                2 => VehicleDecisionAction.Left,
                3 => VehicleDecisionAction.Right,
                4 => VehicleDecisionAction.UTurn,
                _ => VehicleDecisionAction.NoOperation,
            };
        }

        static bool TryGetLoadMapNameFromUI(out string mapId)
        {
            mapId = null;

            try
            {
                var documents = UnityEngine.Object.FindObjectsByType<UIDocument>(FindObjectsSortMode.None);
                if (documents == null || documents.Length == 0)
                {
                    return false;
                }

                for (int i = 0; i < documents.Length; i++)
                {
                    var root = documents[i]?.rootVisualElement;
                    if (root == null)
                    {
                        continue;
                    }

                    var field = root.Q<TextField>("loadMap_name");
                    var value = field?.value;
                    if (!string.IsNullOrEmpty(value))
                    {
                        mapId = value;
                        return true;
                    }
                }

                return false;
            }
            catch
            {
                return false;
            }
        }

    }
}
