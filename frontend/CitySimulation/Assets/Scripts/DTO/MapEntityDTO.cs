using System;
using System.Collections.Generic;
using UnityEngine;

namespace CitySimulation.DTO
{
    [Serializable]
    public enum MapCategory
    {
        TargetPoint,
        Road,
        Building,
        Vehicle,
        TrafficLight
    }

    [Serializable]
    public enum VehicleType
    {
        Normal,
        Emergency
    }

    [Serializable]
    public enum GameDecisionStatus
    {
        NoDecisionNeeded,
        NeedDecision,
        GameCompleted
    }

    [Serializable]
    public class MapEntityDTO
    {
        public string id;
        public MapCategory category;
        public string styleId;
        public Vector3 position;
        public Quaternion rotation;
    }
    [Serializable]
    public class RoadDTO : MapEntityDTO
    {
        public List<Vector3> controlPoints = new();
    }
    [Serializable]
    public class TargetPointDTO : MapEntityDTO
    {
    }

    [Serializable]
    public class BuildingDTO : MapEntityDTO
    {
        public Vector3 size;
    }

    [Serializable]
    public class VehicleDTO : MapEntityDTO
    {
        public VehicleType vehicleType;
        public string currentRoadId;
        public string targetPointId;
        public GameDecisionStatus gameStatus;
    }

    [Serializable]
    public class TrafficLightDTO : MapEntityDTO
    {
        public string currentGreenRoadId;
        public float timeInPhase;
        public List<string> controlledRoadIds = new();
        public GameDecisionStatus gameStatus;
    }
}
