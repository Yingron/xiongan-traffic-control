namespace CitySimulation.Global
{
    // global config
    public static class SimulationConfig
    {
        // =============================
        // Lane
        // =============================
        
        public const float VehicleLaneOffset = 2f;
        
        // =============================
        // Vehicle
        // =============================
        public const float VehicleMaxSpeed = 20f;

        // vehicle position in GameObject center
        public const float VehicleFollowStopDistance = 9f;
        public const float VehicleFollowGoDistance = 10f;
        public const float VehicleNearestQueryDistanceThreshold = 2f;

        // Reward settings for emergency vehicle target-arrival task.
        public const float VehicleRewardPerDecisionStepPenalty = -0.02f;
        public const float VehicleRewardDistancePerMeter = 0.5f;
        public const float VehicleRewardArrivalDistanceThreshold = 1f;
        public const float VehicleRewardArrivalBonusBase = 50f;
        public const float VehicleRewardEarlyArrivalBonusMax = 80f;
        public const float VehicleRewardTimeoutPenaltyBase = -20f;
        public const float VehicleRewardTimeoutRemainingDistancePerMeter = -0.05f;
        public const float VehicleRewardTimeoutPenaltyMin = -50f;
        public const float VehicleArrivalCompleteDistanceThreshold = 4f;

        // Observation normalization scales for MARL inputs.
        public const float RuntimeObservationMapExtentMeters = 1000f;
        public const float RuntimeObservationDistanceScaleMeters = 1000f;

        // =============================
        // Vehicle -- Trunning control
        // =============================

        // Restrict -- (BackendDecisionSendIntervalSeconds+dt) * VehicleMaxSpeed < SemaphoreControlRingOuterRadius - SemaphoreControlRingInnerRadius
        public const float BackendDecisionSendIntervalSeconds = 0.1f;
        public const float SemaphoreControlRingInnerRadius = 10f;
        public const float SemaphoreControlRingOuterRadius = 11f;
        
        
        public const float BackendControlRadius = 11f;
        public const float SemaphoreKeepRadius = 6f;
        public const float VehicleTurnSwitchRoadDistance = 1f;

        // =============================
        // Simulation
        // =============================

        // Default simulation step dt (seconds) for local function interface.
        // 2026-4-7 pre is 0.02
        public const float RuntimeStepDtSeconds = 0.1f;

        public static int RuntimeStepRepeat = 10;
        public static int RuntimeEffectiveVehicleCount = 5;
        // Reward stage: 1=vehicle route reward, 2=traffic-signal reward, 3=sum of both.
        public static int RuntimeRewardStage = 3;
        public static bool RuntimeLowSpeedMode = false;
        public const float RuntimeLowSpeedModePauseSeconds = 1f;
        public const bool EmergencyVehiclesIgnoreLeaderBlocking = false;

        // Runtime observation delay switch, controlled by UI toggle "set_noise".
        public static bool RuntimeObservationDelayEnabled = false;

        // Backend override for delay simulation (higher priority than UI).
        public static bool RuntimeObservationDelayOverrideActive = false;
        public static bool RuntimeObservationDelayOverrideValue = false;

        public static bool RuntimeObservationDelayEffective
            => RuntimeObservationDelayOverrideActive ? RuntimeObservationDelayOverrideValue : RuntimeObservationDelayEnabled;

        // Legacy noise-level fields kept for compatibility with older scenes/scripts.
        public const int RuntimeObservationNoiseDMax = 50;
        // In urban V2X, packet loss is usually low but can rise under occlusion/interference.
        // Use 20% as a practical stress-test upper bound.
        public static float RuntimeObservationMaxPacketLossProbability = 0.2f;
        public static int RuntimeObservationNoiseLevel = 0;

        // Unified observation vector size for all controllable agents.
        public const int UnifiedAgentObsSize = 17;

        // Directed road-graph observation scales and transition costs.
        public const float IntersectionGraphDistanceDeltaScaleMeters = 200f;
        public const float IntersectionGraphTurnCostMeters = 2f;
        public const float IntersectionGraphUTurnCostMeters = 4f;
        public const float IntersectionGraphEndpointTurnCostMeters = 4f;

        // Unified backend action space size for all controllable agents.
        public const int UnifiedAgentActionSpaceSize = 7;

        public const int IntersectionVehicleActionSpaceSize = 5;
        public const int IntersectionSignalActionSpaceSize = 2;

        // Terminal condition: end episode when elapsed simulation time exceeds this limit.
        public const float RuntimeTerminalMaxSeconds = 300f;

        // =============================
        // Traffic
        // =============================

        // Traffic signal green duration in seconds before switching to the other road.
        // Requirement: alternate every 10 seconds.
        // Restrict -- TrafficGreenDurationSeconds > TrafficPhaseExtendSeconds
        public const float TrafficGreenDurationSeconds = 5f;

        // Trigger backend traffic decision when phase countdown crosses this value.
        public const float TrafficControlTriggerCountdownSeconds = 3f;

        // Extend current phase by this duration per accepted extension decision.
        public const float TrafficPhaseExtendSeconds = 3f;

        // Maximum number of phase extensions allowed in one phase cycle.
        public const int TrafficPhaseMaxExtendCount = 2;

        // Maximum forward distance used when observing emergency vehicles for a traffic light.
        public const float TrafficObserveEmergencyVehicleMaxDistance = 60f;

        // Maximum range used when observing traffic congestion around a traffic light.
        public const float TrafficObserveCongestionMaxRange = 50f;

        // Signal reward: positive when emergency vehicles face green, negative when waiting on red.
        public const float TrafficRewardEmergencyGreenPerStep = 0.04f;
        public const float TrafficRewardEmergencyRedWaitPenaltyPerStep = -0.12f;
        public const float TrafficRewardCongestionPenaltyPerVehiclePerStep = -0.005f;
        public const float TrafficRewardSwitchPenalty = -0.15f;
        public const float TrafficRewardKeepMismatchPenalty = -0.05f;

        // Vehicle is controlled by signal only in this annulus [inner, outer].
        // Inside inner radius (entered intersection) or outside outer radius,
        // it is considered unrestricted and can pass.
        public const float TrafficControlRingInnerRadius = 10f;
        public const float TrafficControlRingOuterRadius = 11f;

        // Distance threshold for clustering nearby intersection points.
        public const float TrafficIntersectionMergeEpsilon = 0.5f;
    }
}
