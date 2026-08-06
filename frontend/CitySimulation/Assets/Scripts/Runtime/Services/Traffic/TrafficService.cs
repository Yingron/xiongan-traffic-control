using System;
using System.Collections.Generic;
using System.Linq;
using CitySimulation.DTO;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using CitySimulation.Runtime.Simulation;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Traffic
{
    public sealed partial class TrafficService : IEntityService
    {
        // ===========
        // Data
        // ===========
        readonly List<TrafficLightEntity> trafficLights = new();
        readonly Dictionary<string, TrafficLightEntity> trafficLightById = new();
        readonly Dictionary<string, TurningLock> turningLockByLightId = new();

        ObjectManager objectManager;

        public IReadOnlyList<TrafficLightEntity> TrafficLights => trafficLights;

        // ===========
        // Lifecycle
        // ===========
        public void Initialize(ObjectManager objectManager)
        {
            this.objectManager = objectManager;
            EnsureTrafficLights();
        }

        public void Release()
        {
            ClearTrafficLightsEntity();
            trafficLights.Clear();
            trafficLightById.Clear();
            turningLockByLightId.Clear();
            trafficExtendCountByLightId.Clear();
            ResetEpisodeTrafficControlStats();
            objectManager = null;
        }

        public void RebuildFromRoadIntersections()
        {
            if (objectManager == null)
            {
                return;
            }

            ClearTrafficLightsEntity();
            trafficLights.Clear();
            trafficLightById.Clear();
            turningLockByLightId.Clear();
            trafficExtendCountByLightId.Clear();
            ResetEpisodeTrafficControlStats();

            var roads = objectManager.GetAllEntities().OfType<RoadEntity>().ToList();
            var intersections = FindIntersections(roads, SimulationConfig.TrafficIntersectionMergeEpsilon);

            foreach (var node in intersections.Values)
            {
                var roadIds = node.RoadIds.OrderBy(id => id).Take(2).ToList();
                if (roadIds.Count < 2)
                {
                    continue;
                }

                var dto = new TrafficLightDTO
                {
                    id = BuildStableTrafficLightId(node.AveragePosition, roadIds),
                    category = MapCategory.TrafficLight,
                    styleId = "Empty_TrafficLight",
                    position = node.AveragePosition,
                    rotation = Quaternion.identity,
                    currentGreenRoadId = roadIds[0],
                    timeInPhase = 0f,
                    controlledRoadIds = roadIds
                };

                if (objectManager.CreateObject(dto, need_validate: false) is not TrafficLightEntity light)
                {
                    continue;
                }

                trafficLights.Add(light);
                trafficLightById[light.id] = light;
                turningLockByLightId[light.id] = new TurningLock(roadIds[0], roadIds[1]);
            }

            SortTrafficLightsByPosition();

        }

        public void RebuildFromRoadIntersectionsForMapSave(ObjectManager targetObjectManager)
        {
            objectManager = targetObjectManager ?? objectManager;
            RebuildFromRoadIntersections();
        }

        public void EnsureTrafficLights()
        {
            if (!TryUseExistingTrafficLights())
            {
                RebuildFromRoadIntersections();
            }
        }

        bool TryUseExistingTrafficLights()
        {
            trafficLights.Clear();
            trafficLightById.Clear();
            turningLockByLightId.Clear();
            trafficExtendCountByLightId.Clear();
            ResetEpisodeTrafficControlStats();

            if (objectManager == null)
            {
                return false;
            }

            foreach (var light in objectManager.GetAllEntities().OfType<TrafficLightEntity>())
            {
                if (light == null || string.IsNullOrEmpty(light.id) || light.controlledRoadIds == null || light.controlledRoadIds.Count < 2)
                {
                    continue;
                }

                trafficLights.Add(light);
                trafficLightById[light.id] = light;
                turningLockByLightId[light.id] = new TurningLock(light.controlledRoadIds[0], light.controlledRoadIds[1]);
            }

            SortTrafficLightsByPosition();
            return trafficLights.Count > 0;
        }

        static string BuildStableTrafficLightId(Vector3 position, IReadOnlyList<string> roadIds)
        {
            int x = Mathf.RoundToInt(position.x * 100f);
            int z = Mathf.RoundToInt(position.z * 100f);
            string road0 = roadIds != null && roadIds.Count > 0 ? SanitizeIdPart(roadIds[0]) : "road0";
            string road1 = roadIds != null && roadIds.Count > 1 ? SanitizeIdPart(roadIds[1]) : "road1";
            return $"traffic_{x}_{z}_{road0}_{road1}";
        }

        static string SanitizeIdPart(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "empty";
            }

            return value.Replace(" ", "_").Replace("/", "_").Replace("\\", "_").Replace(":", "_");
        }

        void SortTrafficLightsByPosition()
        {
            trafficLights.Sort((a, b) =>
            {
                if (ReferenceEquals(a, b))
                {
                    return 0;
                }

                if (a == null)
                {
                    return 1;
                }

                if (b == null)
                {
                    return -1;
                }

                int byX = a.position.x.CompareTo(b.position.x);
                if (byX != 0)
                {
                    return byX;
                }

                int byZ = a.position.z.CompareTo(b.position.z);
                if (byZ != 0)
                {
                    return byZ;
                }

                return string.CompareOrdinal(a.id, b.id);
            });
        }

        void ClearTrafficLightsEntity()
        {
            if (objectManager == null && trafficLights.Count == 0)
            {
                return;
            }

            var ids = new HashSet<string>();
            for (int i = 0; i < trafficLights.Count; i++)
            {
                var light = trafficLights[i];
                if (light == null || string.IsNullOrEmpty(light.id))
                {
                    continue;
                }

                ids.Add(light.id);
            }

            if (objectManager != null)
            {
                foreach (var light in objectManager.GetAllEntities().OfType<TrafficLightEntity>())
                {
                    if (light == null || string.IsNullOrEmpty(light.id))
                    {
                        continue;
                    }

                    ids.Add(light.id);
                }
            }

            foreach (var id in ids)
            {
                objectManager?.DestroyObject(id);
            }

            trafficLights.Clear();
            trafficLightById.Clear();
            turningLockByLightId.Clear();
        }

        // ===========
        // Tick
        // ===========
        public void Tick(float dt)
        {
            if (objectManager == null)
            {
                return;
            }

            if (dt <= 0f)
            {
                return;
            }

            float phaseDuration = Mathf.Max(0.0001f, SimulationConfig.TrafficGreenDurationSeconds);

            foreach (var light in trafficLights)
            {
                if (light == null || light.controlledRoadIds == null || light.controlledRoadIds.Count < 2)
                {
                    continue;
                }

                float remainingBefore = phaseDuration - light.timeInPhase;
                light.timeInPhase += dt;
                float remainingAfter = phaseDuration - light.timeInPhase;

                // Trigger control exactly when the countdown crosses 3 seconds.
                TryControlPhaseAtCountdown3(light, remainingBefore, remainingAfter);

                if (light.timeInPhase < phaseDuration)
                {
                    continue;
                }

                SwitchPhase(light);
            }
        }


        // ===========
        // Function
        // ===========
        
        // Query Traffic Lights
        public bool TryGetTrafficLightById(string lightId, out TrafficLightEntity light)
        {
            light = null;

            if (string.IsNullOrEmpty(lightId))
            {
                return false;
            }

            return trafficLightById.TryGetValue(lightId, out light) && light != null;
        }

        /// <summary>
        /// Query whether the vehicle can pass according to the traffic signal in front.
        /// Rule summary:
        /// 1) A signal is considered "in front" only when angle(vehicleForward, toSignal) &lt; 90° (dot &gt; 0).
        /// 2) Signal control applies only in the annulus [10m, 10.5m] around a signal.
        /// 3) Outside this annulus (including after crossing, i.e. inside 10m), vehicle is unrestricted and returns true.
        /// 4) If controlled, return whether the signal currently allows the vehicle's road id.
        /// </summary>
        public bool CanPassForwardSignal(Vector3 vehiclePosition, Quaternion vehicleRotation, string roadId)
        {
            if (!TryGetNearestForwardLight(
                    vehiclePosition,
                    vehicleRotation,
                    roadId,
                    SimulationConfig.TrafficControlRingInnerRadius,
                    SimulationConfig.TrafficControlRingOuterRadius,
                    out var nearestForwardLight,
                    out _))
            {
                return true;
            }

            return string.Equals(nearestForwardLight.currentGreenRoadId, roadId, StringComparison.Ordinal);
        }
        
    }
}
