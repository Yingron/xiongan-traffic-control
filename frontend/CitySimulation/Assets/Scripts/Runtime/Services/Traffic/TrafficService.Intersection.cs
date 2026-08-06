using System.Collections.Generic;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Geometry;
using UnityEngine;

namespace CitySimulation.Runtime.Services.Traffic
{
    public sealed partial class TrafficService
    {
        // ==================
        // FindIntersections
        // ==================
        static Dictionary<string, IntersectionNode> FindIntersections(IReadOnlyList<RoadEntity> roads, float epsilon)
        {
            var map = new Dictionary<string, IntersectionNode>();
            if (roads == null || roads.Count < 2)
            {
                return map;
            }

            for (int i = 0; i < roads.Count; i++)
            {
                var r1 = roads[i];
                if (r1?.controlPoints == null || r1.controlPoints.Count < 2)
                {
                    continue;
                }

                for (int j = i + 1; j < roads.Count; j++)
                {
                    var r2 = roads[j];
                    if (r2?.controlPoints == null || r2.controlPoints.Count < 2)
                    {
                        continue;
                    }

                    for (int a = 0; a < r1.controlPoints.Count - 1; a++)
                    {
                        Vector3 p1 = GeometryUtils.Flatten(r1.controlPoints[a]);
                        Vector3 p2 = GeometryUtils.Flatten(r1.controlPoints[a + 1]);

                        for (int b = 0; b < r2.controlPoints.Count - 1; b++)
                        {
                            Vector3 q1 = GeometryUtils.Flatten(r2.controlPoints[b]);
                            Vector3 q2 = GeometryUtils.Flatten(r2.controlPoints[b + 1]);

                            if (!GeometryUtils.TryIntersectSegmentsXZ(p1, p2, q1, q2, out var hit))
                            {
                                continue;
                            }

                            string key = QuantizeKey(hit, epsilon);
                            if (!map.TryGetValue(key, out var node))
                            {
                                node = new IntersectionNode();
                                map[key] = node;
                            }

                            node.Add(hit, r1.id);
                            node.Add(hit, r2.id);
                        }
                    }
                }
            }

            return map;
        }

        static string QuantizeKey(Vector3 p, float epsilon)
        {
            float safe = Mathf.Max(0.0001f, epsilon);
            int x = Mathf.RoundToInt(p.x / safe);
            int z = Mathf.RoundToInt(p.z / safe);
            return $"{x}_{z}";
        }

        sealed class IntersectionNode
        {
            readonly HashSet<string> roadIds = new();
            Vector3 sum;
            int count;

            public IReadOnlyCollection<string> RoadIds => roadIds;
            public Vector3 AveragePosition => count <= 0 ? Vector3.zero : sum / count;

            public void Add(Vector3 position, string roadId)
            {
                sum += position;
                count++;
                if (!string.IsNullOrEmpty(roadId))
                {
                    roadIds.Add(roadId);
                }
            }
        }
    }
}
