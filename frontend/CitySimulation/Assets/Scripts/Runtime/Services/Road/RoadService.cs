using System.Collections.Generic;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Road
{
    public sealed class RoadService : IEntityService
    {
        ObjectManager objectManager;
        readonly Dictionary<string, LanePointsManager> polylinesByRoadId = new();
        readonly Dictionary<string, ControlPointsManager> controlPointsByRoadId = new();

        // ===========
        // Lifecycle
        // ===========

        public void Initialize(ObjectManager objectManager)
        {
            this.objectManager = objectManager;
            Rebuild();
        }

        public void Release()
        {
            polylinesByRoadId.Clear();
            controlPointsByRoadId.Clear();
            objectManager = null;
        }

        public void Tick(float dt)
        {
        }

        public void Rebuild()
        {
            polylinesByRoadId.Clear();
            controlPointsByRoadId.Clear();
            if (objectManager == null)
            {
                return;
            }

            foreach (var e in objectManager.GetAllEntities())
            {
                if (e is not RoadEntity road)
                {
                    continue;
                }

                if (road.controlPoints == null || road.controlPoints.Count < 2)
                {
                    continue;
                }

                polylinesByRoadId[road.id] = new LanePointsManager(road.controlPoints);
                controlPointsByRoadId[road.id] = new ControlPointsManager(road.controlPoints);
            }
        }

        // ===========================
        // for vehicle move
        // ===========================
        public bool TryGetTargetPose(string roadId, Vector3 currentPosition, float travelDistance, out Vector3 targetPosition, out Quaternion targetRotation)
        {
            targetPosition = currentPosition;
            targetRotation = Quaternion.identity;

            if (string.IsNullOrEmpty(roadId))
            {
                return false;
            }

            if (!polylinesByRoadId.TryGetValue(roadId, out var polyline))
            {
                return false;
            }

            return polyline.TryGetTargetPose(currentPosition, travelDistance, out targetPosition, out targetRotation);
        }

        // `progressS` is the linear distance (meters) along the lane loop measured
        // from the loop start to the projection point of `currentPosition` on the lane loop.
        // It wraps around the closed loop (0 .. laneLoopLength).
        public bool TryGetProgressS(string roadId, Vector3 currentPosition, out float progressS)
        {
            progressS = 0f;

            if (string.IsNullOrEmpty(roadId))
            {
                return false;
            }

            if (!polylinesByRoadId.TryGetValue(roadId, out var polyline))
            {
                return false;
            }

            return polyline.TryGetProgressS(currentPosition, out progressS);
        }

        public bool TryGetLaneLoopLength(string roadId, out float laneLoopLength)
        {
            laneLoopLength = 0f;

            if (string.IsNullOrEmpty(roadId))
            {
                return false;
            }

            if (!polylinesByRoadId.TryGetValue(roadId, out var polyline))
            {
                return false;
            }

            laneLoopLength = polyline.LaneLoopLength;
            return laneLoopLength > 0.0001f;
        }

        // ===========================
        // for vehicle turn
        // ===========================

        // Return the nearest two lane-point sections (pair) to `nearPosition`.
        // This method always attempts to return up to two nearest sections.
        public bool TryGetNearest_Pairof_LanePointSections(string roadId, Vector3 nearPosition, out List<Section> sections)
        {
            sections = new List<Section>();

            if (string.IsNullOrEmpty(roadId))
            {
                return false;
            }

            if (!polylinesByRoadId.TryGetValue(roadId, out var polyline))
            {
                return false;
            }

            return polyline.TryGetNearestSections(nearPosition, 2, out sections);
        }

        // Return the nearest control-point section for `nearPosition`.
        // Caller may inspect `section.Direction` to compute approach sign.
        public bool TryGetNearest_ControlPointSection(string roadId, Vector3 nearPosition, out Section section)
        {
            section = default;

            if (string.IsNullOrEmpty(roadId))
            {
                return false;
            }

            if (!controlPointsByRoadId.TryGetValue(roadId, out var controlPointsManager))
            {
                return false;
            }

            return controlPointsManager.TryGetNearestSection(nearPosition, out section);
        }

        // Returns 1 when the vehicle forward direction is the same as the nearest control-point section direction,
        // and -1 when it is in the opposite direction.
        public bool TryGetDirectionSign(string roadId, Vector3 vehiclePosition, Quaternion vehicleRotation, out int directionSign)
        {
            directionSign = 1;

            if (!TryGetNearest_ControlPointSection(roadId, vehiclePosition, out var section))
            {
                return false;
            }

            Vector3 axis = section.Direction;
            axis.y = 0f;
            if (axis.sqrMagnitude <= 0.0001f)
            {
                return false;
            }
            axis.Normalize();

            Vector3 forward = vehicleRotation * Vector3.forward;
            forward.y = 0f;
            if (forward.sqrMagnitude <= 0.0001f)
            {
                forward = Vector3.forward;
            }
            else
            {
                forward.Normalize();
            }

            float dot = Vector3.Dot(forward, axis);
            directionSign = dot >= 0f ? 1 : -1;
            return true;
        }
        
    }
}
