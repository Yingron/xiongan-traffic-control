using System.Collections.Generic;
using CitySimulation.Geometry;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Road
{
    public sealed class ControlPointsManager
    {
        // - `controlPoints` represent the road centerline (sequence of center control points).
        // - Each road generates two offset lanes from the centerline; positive offset is to the right (right-side offset).
        // ControlSections follow the control point order and represent the forward road direction.

        private readonly List<Vector3> controlPoints;
        private readonly List<Section> controlSections;

        public IReadOnlyList<Vector3> ControlPoints => controlPoints;
        public IReadOnlyList<Section> ControlSections => controlSections;

        public ControlPointsManager(IReadOnlyList<Vector3> inputPoints)
        {
            controlPoints = NormalizeControlPoints(inputPoints);
            controlSections = BuildSections(controlPoints);
        }

        public bool TryGetNearestControlPointSection(Vector3 nearPosition, out Vector3 a, out Vector3 b)
        {
            a = Vector3.zero;
            b = Vector3.zero;

            if (!TryGetNearestSection(nearPosition, out var section))
            {
                return false;
            }

            a = section.Start;
            b = section.End;
            return true;
        }

        public bool TryGetNearestSection(Vector3 nearPosition, out Section section)
        {
            section = default;

            if (controlSections == null || controlSections.Count == 0)
            {
                return false;
            }

            Vector3 flatNear = GeometryUtils.Flatten(nearPosition);
            float bestD2 = float.PositiveInfinity;
            int bestIndex = -1;

            for (int i = 0; i < controlSections.Count; i++)
            {
                var candidate = controlSections[i];
                if (candidate.Direction.sqrMagnitude <= 0.0001f)
                {
                    continue;
                }

                Vector3 projected = GeometryUtils.ProjectPointToSegmentXZ(flatNear, candidate.Start, candidate.End);
                float d2 = (projected - flatNear).sqrMagnitude;
                if (d2 < bestD2)
                {
                    bestD2 = d2;
                    bestIndex = i;
                }
            }

            if (bestIndex < 0)
            {
                return false;
            }

            section = controlSections[bestIndex];
            return true;
        }

        static List<Vector3> NormalizeControlPoints(IReadOnlyList<Vector3> input)
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

        static List<Section> BuildSections(IReadOnlyList<Vector3> points)
        {
            var sections = new List<Section>();

            if (points == null || points.Count < 2)
            {
                return sections;
            }

            for (int i = 0; i < points.Count - 1; i++)
            {
                Vector3 start = points[i];
                Vector3 end = points[i + 1];
                var section = new Section(start, end);
                if (section.Direction.sqrMagnitude <= 0.0001f)
                {
                    continue;
                }

                sections.Add(section);
            }

            return sections;
        }

    }
}
