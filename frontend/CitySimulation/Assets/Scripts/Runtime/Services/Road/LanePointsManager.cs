using System.Collections.Generic;
using CitySimulation.Geometry;
using CitySimulation.Global;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Road
{
    public readonly struct Section
    {
        public Section(Vector3 start, Vector3 end)
        {
            Start = start;
            End = end;
            var direction = end - start;
            direction.y = 0f;
            Direction = direction;
        }

        public Vector3 Start { get; }
        public Vector3 End { get; }
        public Vector3 Direction { get; }
    }

    // -------------------------------------------------------------------------
    // RoadPolyline
    // - Purpose: construct a two-lane offset closed loop from control points
    //   and provide a simple linear travel API for vehicles.
    // - Core API: TryGetTargetPose(currentPosition, travelDistance, out pos, out rot)
    // -------------------------------------------------------------------------
    public sealed class LanePointsManager
    {
        // - `lanePoints` stores the closed-loop sequence of offset lane points. Points are stored counter-clockwise.
        //   The sequence is assembled with the right-side lane first (right-forward), then the left lane in reverse order.
        // - `laneSections` are the line segments connecting `laneLoopPoints` in counter-clockwise order and represent the vehicle travel direction.
        // - These structures allow linear advancement and positioning along the closed loop (e.g., `TryGetTargetPose` API).
        private readonly List<Vector3> lanePoints;
        private readonly List<Section> laneSections;
        private readonly float laneLoopLength;

        public IReadOnlyList<Vector3> LanePoints => lanePoints;
        public IReadOnlyList<Section> LaneSections => laneSections;
        public float LaneLoopLength => laneLoopLength;

        public LanePointsManager(IReadOnlyList<Vector3> inputPoints)
        {
            var basePoints = NormalizeBasePoints(inputPoints);
            lanePoints = BuildLaneLoop(basePoints, SimulationConfig.VehicleLaneOffset);
            laneSections = BuildLaneLoopSections(lanePoints);
            laneLoopLength = ComputeClosedLoopLength(lanePoints);
        }

        // ===========================================================================
        // Helpers — Input normalization
        // Note: the following are utility functions used by RoadPolyline to prepare and manipulate the base control points (flatten Y, remove duplicates).
        // ===========================================================================
        
        static List<Vector3> NormalizeBasePoints(IReadOnlyList<Vector3> input)
        {
            var result = new List<Vector3>(input?.Count ?? 0);
            if (input == null)
            {
                return result;
            }

            for (int i = 0; i < input.Count; i++)
            {
                var p = input[i];
                p.y = 0f;
                AddPointIfDistinct(result, p);
            }

            if (result.Count < 2)
            {
                result.Clear();
            }

            return result;
        }

        static void AddPointIfDistinct(List<Vector3> list, Vector3 p)
        {
            p.y = 0f;
            if (list.Count == 0)
            {
                list.Add(p);
                return;
            }

            if ((list[list.Count - 1] - p).sqrMagnitude > 0.0001f)
            {
                list.Add(p);
            }
        }
        
        // ===========================================================================
        // Helpers — Build lane loop
        // BuildLaneLoop: assemble right/left offset lanes into a single closed loop.
        // ===========================================================================
        static List<Vector3> BuildLaneLoop(IReadOnlyList<Vector3> basePoints, float offset)
        {
            if (basePoints == null || basePoints.Count < 2)
            {
                return new List<Vector3>();
            }

            var rightLane = BuildOffsetLane(basePoints, offset);
            var leftLane = BuildOffsetLane(basePoints, -offset);

            var loop = new List<Vector3>(rightLane.Count + leftLane.Count);

            for (int i = 0; i < rightLane.Count; i++)
            {
                AddPointIfDistinct(loop, rightLane[i]);
            }

            for (int i = leftLane.Count - 1; i >= 0; i--)
            {
                AddPointIfDistinct(loop, leftLane[i]);
            }

            if (loop.Count >= 2 && (loop[0] - loop[loop.Count - 1]).sqrMagnitude <= 0.0001f)
            {
                loop.RemoveAt(loop.Count - 1);
            }

            return loop;
        }

        // Use intersection of adjacent offset lines as lane control points so that
        // convex and concave corners are handled correctly when driving along
        // the offset lane.
        static List<Vector3> BuildOffsetLane(IReadOnlyList<Vector3> basePoints, float offset)
        {
            var lane = new List<Vector3>(basePoints.Count);

            for (int i = 0; i < basePoints.Count; i++)
            {
                Vector3 p = basePoints[i];
                p.y = 0f;

                if (i == 0)
                {
                    Vector3 d = GeometryUtils.SafeDirection(basePoints[0], basePoints[1]);
                    lane.Add(p + GeometryUtils.RightNormal(d) * offset);
                    continue;
                }

                if (i == basePoints.Count - 1)
                {
                    Vector3 d = GeometryUtils.SafeDirection(basePoints[i - 1], basePoints[i]);
                    lane.Add(p + GeometryUtils.RightNormal(d) * offset);
                    continue;
                }

                Vector3 dPrev = GeometryUtils.SafeDirection(basePoints[i - 1], basePoints[i]);
                Vector3 dNext = GeometryUtils.SafeDirection(basePoints[i], basePoints[i + 1]);

                Vector3 p1 = p + GeometryUtils.RightNormal(dPrev) * offset;
                Vector3 p2 = p + GeometryUtils.RightNormal(dNext) * offset;

                if (GeometryUtils.TryIntersectLinesXZ(p1, dPrev, p2, dNext, out Vector3 intersect))
                {
                    intersect.y = 0f;
                    lane.Add(intersect);
                }
                else
                {
                    lane.Add(p2);
                }
            }

            return lane;
        }
        
        // ===========================================================================
        // Section - vector of laneLoopPoints
        // ===========================================================================
        static List<Section> BuildLaneLoopSections(IReadOnlyList<Vector3> loop)
        {
            var sections = new List<Section>();

            if (loop == null || loop.Count < 2)
            {
                return sections;
            }

            for (int i = 0; i < loop.Count; i++)
            {
                Vector3 start = loop[i];
                Vector3 end = loop[(i + 1) % loop.Count];
                var section = new Section(start, end);
                if (section.Direction.sqrMagnitude <= 0.0001f)
                {
                    continue;
                }

                sections.Add(section);
            }

            return sections;
        }
        public bool TryGetNearestSections(Vector3 nearPosition, int count, out List<Section> sections)
        {
            sections = new List<Section>();

            if (count <= 0)
            {
                return false;
            }

            if (laneSections == null || laneSections.Count == 0)
            {
                return false;
            }

            var candidates = new List<(Section section, float distanceSquared)>();
            Vector3 flatNear = GeometryUtils.Flatten(nearPosition);

            for (int i = 0; i < laneSections.Count; i++)
            {
                var section = laneSections[i];
                if (section.Direction.sqrMagnitude <= 0.0001f)
                {
                    continue;
                }

                Vector3 a = GeometryUtils.Flatten(section.Start);
                Vector3 b = GeometryUtils.Flatten(section.End);

                Vector3 projected = GeometryUtils.ProjectPointToSegmentXZ(flatNear, a, b);
                float distanceSquared = (projected - flatNear).sqrMagnitude;
                candidates.Add((section, distanceSquared));
            }

            if (candidates.Count == 0)
            {
                return false;
            }

            candidates.Sort((x, y) => x.distanceSquared.CompareTo(y.distanceSquared));

            int takeCount = Mathf.Min(count, candidates.Count);
            for (int i = 0; i < takeCount; i++)
            {
                sections.Add(candidates[i].section);
            }

            return sections.Count > 0;
        }

        // ===========================================================================
        // Helpers - ComputeClosedLoopLength
        // ===========================================================================
        static float ComputeClosedLoopLength(IReadOnlyList<Vector3> loop)
        {
            if (loop == null || loop.Count < 2)
            {
                return 0f;
            }

            float sum = 0f;
            for (int i = 0; i < loop.Count; i++)
            {
                Vector3 a = loop[i];
                Vector3 b = loop[(i + 1) % loop.Count];
                sum += Vector3.Distance(a, b);
            }

            return sum;
        }
        
        // ===================================================================
        // Core API — TryGetTargetPose
        // Given a world-space position and a forward linear distance (meters),
        // locate the nearest point on the precomputed lane loop and advance
        // forward along the loop by the specified distance. Returns the target
        // position and an orientation facing the forward direction on the loop.
        // ===================================================================
        public bool TryGetTargetPose(Vector3 currentPosition, float travelDistance, out Vector3 targetPosition, out Quaternion targetRotation)
        {
            targetPosition = currentPosition;
            targetRotation = Quaternion.identity;

            if (lanePoints == null || lanePoints.Count < 2)
            {
                return false;
            }

            if (laneLoopLength <= 0.0001f)
            {
                return false;
            }

            if (!TryLocateOnLoop(currentPosition, out int segmentIndex, out float segmentT, out Vector3 projected))
            {
                return false;
            }

            float remain = Mathf.Max(0f, travelDistance);
            if (remain > laneLoopLength)
            {
                remain %= laneLoopLength;
            }

            int idx = segmentIndex;
            float t = segmentT;
            Vector3 current = projected;

            for (int safe = 0; safe < lanePoints.Count + 2; safe++)
            {
                Vector3 a = lanePoints[idx];
                Vector3 b = lanePoints[(idx + 1) % lanePoints.Count];
                Vector3 ab = b - a;
                float segLen = ab.magnitude;

                if (segLen <= 0.0001f)
                {
                    idx = (idx + 1) % lanePoints.Count;
                    t = 0f;
                    continue;
                }

                Vector3 dir = ab / segLen;
                float available = segLen * (1f - Mathf.Clamp01(t));
                if (remain <= available)
                {
                    targetPosition = current + dir * remain;
                    targetPosition.y = 0f;
                    targetRotation = Quaternion.LookRotation(dir, Vector3.up);
                    return true;
                }

                remain -= available;
                idx = (idx + 1) % lanePoints.Count;
                t = 0f;
                current = lanePoints[idx];
            }

            Vector3 lastA = lanePoints[idx];
            Vector3 lastB = lanePoints[(idx + 1) % lanePoints.Count];
            Vector3 lastDir = (lastB - lastA).sqrMagnitude <= 0.0001f ? Vector3.forward : (lastB - lastA).normalized;
            targetPosition = lastA;
            targetRotation = Quaternion.LookRotation(lastDir, Vector3.up);
            return true;
        }

        public bool TryGetProgressS(Vector3 currentPosition, out float progressS)
        {
            progressS = 0f;

            if (lanePoints == null || lanePoints.Count < 2)
            {
                return false;
            }

            if (laneLoopLength <= 0.0001f)
            {
                return false;
            }

            if (!TryLocateOnLoop(currentPosition, out int segmentIndex, out float segmentT, out _))
            {
                return false;
            }

            float segmentLength = Vector3.Distance(
                lanePoints[segmentIndex],
                lanePoints[(segmentIndex + 1) % lanePoints.Count]);

            progressS = DistanceBeforeSegment(segmentIndex) + Mathf.Clamp01(segmentT) * segmentLength;
            if (progressS >= laneLoopLength)
            {
                progressS %= laneLoopLength;
            }

            return true;
        }

        float DistanceBeforeSegment(int segmentIndex)
        {
            float sum = 0f;
            for (int i = 0; i < segmentIndex; i++)
            {
                sum += Vector3.Distance(lanePoints[i], lanePoints[(i + 1) % lanePoints.Count]);
            }

            return sum;
        }

        bool TryLocateOnLoop(Vector3 currentPosition, out int segmentIndex, out float segmentT, out Vector3 projected)
        {
            ///<return> segmentT is precent of segment </return>
            segmentIndex = -1;
            segmentT = 0f;
            projected = Vector3.zero;

            if (lanePoints == null || lanePoints.Count < 2)
            {
                return false;
            }

            currentPosition.y = 0f;
            float bestD2 = float.PositiveInfinity;

            for (int i = 0; i < lanePoints.Count; i++)
            {
                Vector3 a = lanePoints[i];
                Vector3 b = lanePoints[(i + 1) % lanePoints.Count];
                Vector3 ab = b - a;
                float len2 = ab.sqrMagnitude;
                if (len2 <= 0.0001f)
                {
                    continue;
                }

                float t = Vector3.Dot(currentPosition - a, ab) / len2;
                t = Mathf.Clamp01(t);
                Vector3 proj = a + ab * t;
                float d2 = (currentPosition - proj).sqrMagnitude;

                if (d2 < bestD2)
                {
                    bestD2 = d2;
                    segmentIndex = i;
                    segmentT = t;
                    projected = proj;
                }
            }

            return segmentIndex >= 0;
        }

    }
}