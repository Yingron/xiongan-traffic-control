using UnityEngine;
using System.Collections.Generic;

namespace CitySimulation.Geometry
{
    public static class GeometryUtils
    {
        public static Vector3 Flatten(Vector3 p)
        {
            p.y = 0f;
            return p;
        }

        /// <summary>
        /// Return true if <paramref name="currentPosition"/> is within
        /// <paramref name="radius"/> of <paramref name="targetPosition"/> on the XZ plane.
        /// </summary>
        public static bool IsNearTarget(Vector3 currentPosition, Vector3 targetPosition, float radius)
        {
            return IsNearTarget(currentPosition, targetPosition, radius, out _);
        }

        /// <summary>
        /// Return true if <paramref name="currentPosition"/> is within
        /// <paramref name="radius"/> of <paramref name="targetPosition"/> on the XZ plane,
        /// and output current XZ-plane distance.
        /// </summary>
        public static bool IsNearTarget(Vector3 currentPosition, Vector3 targetPosition, float radius, out float currentDistance)
        {
            if (radius < 0f)
            {
                radius = 0f;
            }

            currentPosition.y = 0f;
            targetPosition.y = 0f;
            float sqrDistance = (currentPosition - targetPosition).sqrMagnitude;
            currentDistance = Mathf.Sqrt(sqrDistance);
            return sqrDistance <= radius * radius;
        }

        /// <summary>
        /// Return true if <paramref name="point"/> is within <paramref name="radius"/>
        /// of the segment defined by <paramref name="segA"/>-<paramref name="segB"/> on the XZ plane.
        /// </summary>
        public static bool IsPointNearSegmentXZ(Vector3 point, Vector3 segA, Vector3 segB, float radius)
        {
            if (radius < 0f)
            {
                radius = 0f;
            }

            Vector3 proj = ProjectPointToSegmentXZ(point, segA, segB);
            proj.y = 0f;
            point.y = 0f;
            return (proj - point).sqrMagnitude <= radius * radius;
        }

        /// <summary>
        /// Project a point onto the segment defined by <paramref name="segA"/>-<paramref name="segB"/>
        /// and return the closest point on that segment, computed on the XZ plane.
        /// If the segment length is nearly zero, returns <paramref name="segA"/>.
        /// </summary>
        /// <param name="point">Point to project.</param>
        /// <param name="segA">Segment start.</param>
        /// <param name="segB">Segment end.</param>
        /// <returns>Projected point on the segment (y set to 0).</returns>
        public static Vector3 ProjectPointToSegmentXZ(Vector3 point, Vector3 segA, Vector3 segB)
        {
            Vector3 ab = segB - segA;
            ab.y = 0f;
            float len2 = ab.sqrMagnitude;
            if (len2 <= 0.0001f)
            {
                return segA;
            }

            float t = Vector3.Dot(point - segA, ab) / len2;
            t = Mathf.Clamp01(t);
            Vector3 proj = segA + ab * t;
            proj.y = 0f;
            return proj;
        }

        /// <summary>
        /// Try to intersect two infinite lines on the XZ plane.
        /// Each line is specified by a point and a direction vector.
        /// Returns true and sets <paramref name="intersection"/> when lines are not parallel.
        /// </summary>
        public static bool TryIntersectLinesXZ(Vector3 p1, Vector3 d1, Vector3 p2, Vector3 d2, out Vector3 intersection)
        {
            intersection = Vector3.zero;

            Vector2 a = new(p1.x, p1.z);
            Vector2 b = new(d1.x, d1.z);
            Vector2 c = new(p2.x, p2.z);
            Vector2 d = new(d2.x, d2.z);

            float det = b.x * d.y - b.y * d.x;
            if (Mathf.Abs(det) <= 1e-5f)
            {
                return false;
            }

            Vector2 ac = c - a;
            float t = (ac.x * d.y - ac.y * d.x) / det;
            Vector2 inter = a + b * t;
            intersection = new Vector3(inter.x, 0f, inter.y);
            return true;
        }

        /// <summary>
        /// Try to intersect two segments on the XZ plane. Returns true and sets
        /// <paramref name="intersection"/> when the segments intersect (including endpoints).
        /// </summary>
        public static bool TryIntersectSegmentsXZ(Vector3 a1, Vector3 a2, Vector3 b1, Vector3 b2, out Vector3 intersection)
        {
            intersection = Vector3.zero;

            Vector2 p = new(a1.x, a1.z);
            Vector2 r = new(a2.x - a1.x, a2.z - a1.z);
            Vector2 q = new(b1.x, b1.z);
            Vector2 s = new(b2.x - b1.x, b2.z - b1.z);

            float rxs = Cross(r, s);
            if (Mathf.Abs(rxs) <= 1e-5f)
            {
                return false;
            }

            Vector2 qp = q - p;
            float t = Cross(qp, s) / rxs;
            float u = Cross(qp, r) / rxs;

            if (t < 0f || t > 1f || u < 0f || u > 1f)
            {
                return false;
            }

            Vector2 hit = p + t * r;
            intersection = new Vector3(hit.x, 0f, hit.y);
            return true;
        }

        /// <summary>
        /// 2D cross product (scalar) for vectors in the XZ plane represented as Vector2.
        /// Equivalent to a.x * b.y - a.y * b.x.
        /// </summary>
        public static float Cross(Vector2 a, Vector2 b)
        {
            return a.x * b.y - a.y * b.x;
        }

        public static float SqrDistancePointSegmentXZ(Vector3 p, Vector3 a, Vector3 b)
        {
            Vector3 proj = ProjectPointToSegmentXZ(p, a, b);
            p.y = 0f;
            return (p - proj).sqrMagnitude;
        }

        public static float MinSqrDistanceToPolylineXZ(Vector3 p, IReadOnlyList<Vector3> pts)
        {
            if (pts == null || pts.Count < 2)
            {
                return float.MaxValue;
            }

            float best = float.MaxValue;
            for (int i = 0; i < pts.Count - 1; i++)
            {
                float d = SqrDistancePointSegmentXZ(p, pts[i], pts[i + 1]);
                if (d < best)
                {
                    best = d;
                }
            }

            return best;
        }

        /// <summary>
        /// Return the normalized direction from a to b on XZ plane.
        /// If too short, returns Vector3.forward.
        /// </summary>
        public static Vector3 SafeDirection(Vector3 a, Vector3 b)
        {
            var d = b - a;
            d.y = 0f;
            return d.sqrMagnitude <= 0.0001f ? Vector3.forward : d.normalized;
        }

        /// <summary>
        /// Return unit right-hand normal on XZ plane.
        /// If input direction is too short, returns Vector3.right.
        /// </summary>
        public static Vector3 RightNormal(Vector3 dir)
        {
            dir.y = 0f;
            if (dir.sqrMagnitude <= 0.0001f)
            {
                return Vector3.right;
            }

            return Vector3.Cross(Vector3.up, dir.normalized).normalized;
        }

        /// <summary>
        /// Compute heading-to-target signed angle features on the XZ plane.
        /// sin/cos represent the signed angle from the entity forward direction to the direction-to-target.
        /// distance is the XZ-plane distance to target.
        /// </summary>
        public static void GetHeadingToTargetSinCosXZ(
            Vector3 position,
            Quaternion rotation,
            Vector3 targetPosition,
            out float sinTheta,
            out float cosTheta,
            out float distance)
        {
            Vector3 toTarget3 = targetPosition - position;
            var toTarget = new Vector2(toTarget3.x, toTarget3.z);
            distance = toTarget.magnitude;
            if (distance <= 1e-6f)
            {
                sinTheta = 0f;
                cosTheta = 1f;
                distance = 0f;
                return;
            }

            Vector3 forward3 = rotation * Vector3.forward;
            var forward = new Vector2(forward3.x, forward3.z);
            float forwardMag = forward.magnitude;
            if (forwardMag <= 1e-6f)
            {
                forward = new Vector2(0f, 1f);
            }
            else
            {
                forward /= forwardMag;
            }

            toTarget /= distance;

            cosTheta = Vector2.Dot(forward, toTarget);
            sinTheta = Cross(forward, toTarget);
        }

    }
}
