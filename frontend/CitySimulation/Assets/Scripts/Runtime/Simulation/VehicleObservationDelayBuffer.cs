using System.Collections.Generic;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    public struct VehicleObservationSnapshot
    {
        public float PositionX;
        public float PositionZ;
        public float SinThetaToTarget;
        public float CosThetaToTarget;
        public float DistanceToTarget;
        public float VehicleFromDir;
        public float StraightTargetDelta;
        public float LeftTargetDelta;
        public float RightTargetDelta;
        public float UTurnTargetDelta;
    }

    /// <summary>
    /// Simulates an urban V2X observation link. A lost update makes the controller
    /// retain the last successfully received observation, so consecutive losses
    /// naturally produce increasing observation delay.
    /// </summary>
    public sealed class VehicleObservationDelayBuffer
    {
        // Even a short link may be affected by urban obstruction/interference.
        // The remaining probability grows quadratically with normalized distance.
        const float UrbanPacketLossFloorRatio = 0.35f;
        const float DistanceExponent = 2f;

        readonly struct TimestampedSnapshot
        {
            public TimestampedSnapshot(VehicleObservationSnapshot snapshot, int sequence)
            {
                Snapshot = snapshot;
                Sequence = sequence;
            }

            public VehicleObservationSnapshot Snapshot { get; }
            public int Sequence { get; }
        }

        readonly Dictionary<string, TimestampedSnapshot> lastDeliveredByLink = new();
        readonly Dictionary<string, int> observationSequenceByVehicleId = new();
        readonly List<float> packetLossProbabilities = new();
        readonly List<int> staleObservationAgeSteps = new();
        int observationSendCount;
        int staleObservationCount;

        public VehicleObservationSnapshot GetSnapshotForSend(
            string vehicleId,
            VehicleObservationSnapshot currentSnapshot,
            bool delayEnabled,
            float maxPacketLossProbability,
            float nearestForwardLightDistance,
            float maxRelevantDistance)
        {
            string linkKey = vehicleId ?? string.Empty;
            var snapshotToUse = currentSnapshot;
            observationSequenceByVehicleId.TryGetValue(linkKey, out int currentSequence);
            observationSequenceByVehicleId[linkKey] = currentSequence + 1;
            observationSendCount++;

            if (!delayEnabled)
            {
                packetLossProbabilities.Add(0f);
                StoreDeliveredSnapshot(linkKey, currentSnapshot, currentSequence);
                return snapshotToUse;
            }

            bool shouldUseHistorical = ShouldUseHistoricalObservation(
                maxPacketLossProbability,
                nearestForwardLightDistance,
                maxRelevantDistance,
                out float packetLossProbability);
            packetLossProbabilities.Add(packetLossProbability);

            if (shouldUseHistorical
                && TryGetLastDeliveredSnapshot(linkKey, out var historicalSnapshot, out int historicalSequence))
            {
                snapshotToUse = historicalSnapshot;
                staleObservationCount++;
                staleObservationAgeSteps.Add(Mathf.Max(1, currentSequence - historicalSequence));
            }
            else
            {
                // A successful update replaces the receiver's retained observation.
                // The first update is also delivered so the controller is never
                // initialized with an artificial all-zero observation.
                StoreDeliveredSnapshot(linkKey, currentSnapshot, currentSequence);
            }
            return snapshotToUse;
        }

        public void GetEpisodeStats(
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
            sendCount = observationSendCount;
            staleCount = staleObservationCount;
            staleRatio = sendCount > 0 ? (float)staleCount / sendCount : 0f;
            packetLossProbabilityMean = Mean(packetLossProbabilities);
            packetLossProbabilityP95 = Percentile95(packetLossProbabilities);
            observationAgeStepsMean = Mean(staleObservationAgeSteps);
            observationAgeStepsP95 = Percentile95(staleObservationAgeSteps);
            float secondsPerDecisionStep =
                SimulationConfig.RuntimeStepDtSeconds * Mathf.Max(1, SimulationConfig.RuntimeStepRepeat);
            observationAgeSecondsMean = observationAgeStepsMean * secondsPerDecisionStep;
            observationAgeSecondsP95 = observationAgeStepsP95 * secondsPerDecisionStep;
        }

        public void Cleanup(HashSet<string> activeVehicleIds)
        {
            if (activeVehicleIds == null)
            {
                return;
            }

            var staleKeys = new List<string>();
            foreach (var key in lastDeliveredByLink.Keys)
            {
                if (!activeVehicleIds.Contains(key))
                {
                    staleKeys.Add(key);
                }
            }

            for (int i = 0; i < staleKeys.Count; i++)
            {
                lastDeliveredByLink.Remove(staleKeys[i]);
                observationSequenceByVehicleId.Remove(staleKeys[i]);
            }
        }

        public void Clear()
        {
            lastDeliveredByLink.Clear();
            observationSequenceByVehicleId.Clear();
            packetLossProbabilities.Clear();
            staleObservationAgeSteps.Clear();
            observationSendCount = 0;
            staleObservationCount = 0;
        }

        public static string ResolveVehicleObservationKey(IReadOnlyList<VehicleEntity> emergencyVehicles, int index)
        {
            if (emergencyVehicles != null && index >= 0 && index < emergencyVehicles.Count)
            {
                var vehicle = emergencyVehicles[index];
                if (vehicle != null && !string.IsNullOrEmpty(vehicle.id))
                {
                    return vehicle.id;
                }
            }

            return $"__vehicle_obs_index_{index}";
        }

        static bool ShouldUseHistoricalObservation(
            float maxPacketLossProbability,
            float nearestForwardLightDistance,
            float maxRelevantDistance,
            out float packetLossProbability)
        {
            packetLossProbability = ComputePacketLossProbability(
                maxPacketLossProbability,
                nearestForwardLightDistance,
                maxRelevantDistance);

            return Random.value < packetLossProbability;
        }

        public static float ComputePacketLossProbability(
            float maxPacketLossProbability,
            float nearestForwardLightDistance,
            float maxRelevantDistance)
        {
            // If no configured max loss, no loss occurs.
            if (maxPacketLossProbability <= 0f)
            {
                return 0f;
            }

            float configuredMaximum = Mathf.Clamp01(maxPacketLossProbability);

            // If no valid serving link exists, use the configured maximum rather
            // than silently exceeding the experiment's requested stress level.
            if (nearestForwardLightDistance < 0f || !float.IsFinite(nearestForwardLightDistance))
            {
                return configuredMaximum;
            }

            /*
             Reproducible urban V2X stress model:

               p_loss(d) = p_max * [rho + (1-rho) * (d/d_max)^eta]

             rho represents distance-independent blockage/interference, while the
             second term models distance-dependent degradation. This guarantees:
             (1) non-zero stress near an intersection,
             (2) monotonic degradation with distance, and
             (3) p_loss never exceeds the backend-controlled p_max.
            */
            float distanceScale = Mathf.Max(1f, maxRelevantDistance);
            float normalizedDistance = Mathf.Clamp01(nearestForwardLightDistance / distanceScale);
            float distanceFactor = Mathf.Pow(normalizedDistance, DistanceExponent);
            float stressFactor = Mathf.Lerp(
                UrbanPacketLossFloorRatio,
                1f,
                distanceFactor);
            return configuredMaximum * stressFactor;
        }

        bool TryGetLastDeliveredSnapshot(
            string vehicleId,
            out VehicleObservationSnapshot snapshot,
            out int sequence)
        {
            snapshot = default;
            sequence = 0;

            if (string.IsNullOrEmpty(vehicleId)
                || !lastDeliveredByLink.TryGetValue(vehicleId, out var delivered))
            {
                return false;
            }

            snapshot = delivered.Snapshot;
            sequence = delivered.Sequence;
            return true;
        }

        void StoreDeliveredSnapshot(string vehicleId, VehicleObservationSnapshot snapshot, int sequence)
        {
            if (string.IsNullOrEmpty(vehicleId))
            {
                return;
            }

            lastDeliveredByLink[vehicleId] = new TimestampedSnapshot(snapshot, sequence);
        }

        static float Mean(IReadOnlyList<float> values)
        {
            if (values == null || values.Count == 0)
            {
                return 0f;
            }

            float sum = 0f;
            for (int i = 0; i < values.Count; i++)
            {
                sum += values[i];
            }
            return sum / values.Count;
        }

        static float Mean(IReadOnlyList<int> values)
        {
            if (values == null || values.Count == 0)
            {
                return 0f;
            }

            long sum = 0;
            for (int i = 0; i < values.Count; i++)
            {
                sum += values[i];
            }
            return (float)sum / values.Count;
        }

        static float Percentile95(IReadOnlyList<float> values)
        {
            if (values == null || values.Count == 0)
            {
                return 0f;
            }

            var sorted = new List<float>(values);
            sorted.Sort();
            int index = Mathf.Clamp(Mathf.CeilToInt(sorted.Count * 0.95f) - 1, 0, sorted.Count - 1);
            return sorted[index];
        }

        static float Percentile95(IReadOnlyList<int> values)
        {
            if (values == null || values.Count == 0)
            {
                return 0f;
            }

            var sorted = new List<int>(values);
            sorted.Sort();
            int index = Mathf.Clamp(Mathf.CeilToInt(sorted.Count * 0.95f) - 1, 0, sorted.Count - 1);
            return sorted[index];
        }
    }
}
