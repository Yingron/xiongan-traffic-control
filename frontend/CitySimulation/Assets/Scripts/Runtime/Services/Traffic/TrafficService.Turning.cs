using System;
using System.Collections.Generic;
using System.Linq;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Geometry;
using CitySimulation.Global;
using CitySimulation.Runtime.Services.Road;
using CitySimulation.Runtime.Services.Vehicle;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Traffic
{
    public sealed partial class TrafficService
    {
        // ===========
        // Turning
        // ===========

        // Function - Find forward and nearest light
        public bool TryGetNearestForwardLight(
            Vector3 vehiclePosition,
            Quaternion vehicleRotation,
            string roadId,
            float minDistance,
            float maxDistance,
            out TrafficLightEntity nearestForwardLight,
            out float nearestDistance)
        {
            nearestForwardLight = null;
            nearestDistance = float.PositiveInfinity;

            if (string.IsNullOrEmpty(roadId) || trafficLights.Count == 0)
            {
                return false;
            }

            float min = Mathf.Max(0f, minDistance);
            float max = Mathf.Max(min, maxDistance);

            var forward = vehicleRotation * Vector3.forward;
            forward.y = 0f;
            if (forward.sqrMagnitude <= 0.0001f)
            {
                forward = Vector3.forward;
            }
            else
            {
                forward.Normalize();
            }

            for (int i = 0; i < trafficLights.Count; i++)
            {
                var light = trafficLights[i];
                if (light == null)
                {
                    continue;
                }

                if (light.controlledRoadIds == null || !light.controlledRoadIds.Contains(roadId))
                {
                    continue;
                }

                Vector3 toSignal = light.position - vehiclePosition;
                toSignal.y = 0f;

                float dist = toSignal.magnitude;
                if (dist <= 0.0001f)
                {
                    continue;
                }

                if (Vector3.Dot(toSignal / dist, forward) <= 0f)
                {
                    continue;
                }

                if (dist < min || dist > max)
                {
                    continue;
                }

                if (dist < nearestDistance)
                {
                    nearestDistance = dist;
                    nearestForwardLight = light;
                }
            }

            return nearestForwardLight != null;
        }

        // Function - Turning point calculation , only calculate Left and Right
        public bool TryGetTurningPointOnTargetRightLane(
            TrafficLightEntity light,
            Vector3 currentPosition,
            Quaternion currentRotation,
            string targetRoadId,
            VehicleDecisionAction action,
            out Vector3 turnPoint)
        {
            turnPoint = light != null ? light.position : currentPosition;

            if (light == null || string.IsNullOrEmpty(targetRoadId))
            {
                return false;
            }

            if (action != VehicleDecisionAction.Left && action != VehicleDecisionAction.Right)
            {
                turnPoint = light.position;
                return true;
            }

            Vector3 currentDirection = currentRotation * Vector3.forward;
            currentDirection.y = 0f;
            if (currentDirection.sqrMagnitude <= 0.0001f)
            {
                currentDirection = Vector3.forward;
            }
            else
            {
                currentDirection.Normalize();
            }

            // Get nearest sections from both travel directions (right/left lanes) on the target road.
            if (GameServices.RoadService == null
                || !GameServices.RoadService.TryGetNearest_Pairof_LanePointSections(targetRoadId, light.position, out var nearestSections))
            {
                return false;
            }

            Vector3 turnDirection = action == VehicleDecisionAction.Left
                ? Quaternion.Euler(0f, -90f, 0f) * currentDirection
                : Quaternion.Euler(0f, 90f, 0f) * currentDirection;

            bool hasCandidate = false;
            float bestDistance = float.PositiveInfinity;

            for (int i = 0; i < nearestSections.Count; i++)
            {
                Vector3 targetDir = nearestSections[i].Direction;
                if (targetDir.sqrMagnitude <= 0.0001f)
                {
                    continue;
                }

                targetDir.Normalize();

                float dotTurn = Vector3.Dot(turnDirection, targetDir);
                if (dotTurn <= 0f)
                {
                    continue;
                }

                if (!GeometryUtils.TryIntersectLinesXZ(
                        currentPosition,
                        currentDirection,
                        nearestSections[i].Start,
                        nearestSections[i].Direction,
                        out var intersection))
                {
                    continue;
                }

                float distanceToLight = (intersection - light.position).sqrMagnitude;
                if (distanceToLight < bestDistance)
                {
                    bestDistance = distanceToLight;
                    turnPoint = intersection;
                    hasCandidate = true;
                }
            }

            if (hasCandidate)
            {
                return true;
            }

            turnPoint = light.position;
            return true;
        }

        // Helper - Try Get Alternative RoadId
        public bool TryGetAlternativeRoadId(TrafficLightEntity light, string currentRoadId, out string targetRoadId)
        {
            targetRoadId = null;

            if (light == null || light.controlledRoadIds == null || light.controlledRoadIds.Count == 0)
            {
                return false;
            }

            for (int i = 0; i < light.controlledRoadIds.Count; i++)
            {
                string roadId = light.controlledRoadIds[i];
                if (!string.Equals(roadId, currentRoadId, StringComparison.Ordinal))
                {
                    targetRoadId = roadId;
                    return true;
                }
            }

            return false;
        }
        
        // Turning - Lock management
        public bool CanEnterTurningLock(string lightId, string roadId, int directionSign)
        {
            if (string.IsNullOrEmpty(lightId) || string.IsNullOrEmpty(roadId))
            {
                return true;
            }

            if (!turningLockByLightId.TryGetValue(lightId, out var turningLock))
            {
                return true;
            }

            return turningLock.CanEnter(roadId, directionSign);
        }

        public bool TryAcquireTurningLock(string lightId, string roadId, int directionSign, string vehicleId)
        {
            if (string.IsNullOrEmpty(lightId) || string.IsNullOrEmpty(roadId) || string.IsNullOrEmpty(vehicleId))
            {
                return false;
            }

            if (!turningLockByLightId.TryGetValue(lightId, out var turningLock))
            {
                return false;
            }

            return turningLock.TryAcquire(roadId, directionSign, vehicleId);
        }

        public bool TryAcquireUTurnLock(string lightId, string vehicleId)
        {
            if (string.IsNullOrEmpty(lightId) || string.IsNullOrEmpty(vehicleId))
            {
                return false;
            }

            return turningLockByLightId.TryGetValue(lightId, out var turningLock)
                && turningLock.TryAcquireExclusive(vehicleId);
        }

        public bool CanExecuteAtomicUTurn(TrafficLightEntity light, string currentRoadId)
        {
            return TryGetAlternativeRoadId(light, currentRoadId, out _);
        }

        public bool TryGetAtomicUTurnTurningPoint(
            TrafficLightEntity light,
            Vector3 currentPosition,
            Quaternion currentRotation,
            string targetRoadId,
            int phase,
            out Vector3 turnPoint)
        {
            // Both internal phases are geometric left turns, but they target
            // different roads and are hidden behind one backend UTurn action.
            if (phase != 1 && phase != 2)
            {
                turnPoint = light != null ? light.position : currentPosition;
                return false;
            }

            return TryGetTurningPointOnTargetRightLane(
                light,
                currentPosition,
                currentRotation,
                targetRoadId,
                VehicleDecisionAction.Left,
                out turnPoint);
        }

        public void ReleaseTurningLock(string lightId, string roadId, int directionSign, string vehicleId)
        {
            if (string.IsNullOrEmpty(lightId) || string.IsNullOrEmpty(roadId) || string.IsNullOrEmpty(vehicleId))
            {
                return;
            }

            if (!turningLockByLightId.TryGetValue(lightId, out var turningLock))
            {
                return;
            }

            turningLock.Release(roadId, directionSign, vehicleId);
        }

        public void ReleaseTurningLockByVehicle(string lightId, string vehicleId)
        {
            if (string.IsNullOrEmpty(lightId) || string.IsNullOrEmpty(vehicleId))
            {
                return;
            }

            if (!turningLockByLightId.TryGetValue(lightId, out var turningLock))
            {
                return;
            }

            turningLock.ReleaseAll(vehicleId);
        }
        

    }
}
