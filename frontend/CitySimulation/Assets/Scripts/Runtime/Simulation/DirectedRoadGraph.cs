using System;
using System.Collections.Generic;
using System.Linq;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;
using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    /// <summary>
    /// Directed shortest-path graph over road centerlines. A node is a road
    /// event (endpoint, intersection, or target) plus a travel direction.
    /// </summary>
    sealed class DirectedRoadGraph
    {
        const float MergeEpsilon = 0.05f;

        readonly TrafficService trafficService;
        readonly Dictionary<string, RoadGeometry> roads = new();
        readonly Dictionary<string, TargetGraph> targetGraphs = new();

        public DirectedRoadGraph(ObjectManager objectManager, TrafficService trafficService)
        {
            this.trafficService = trafficService;
            if (objectManager == null)
            {
                return;
            }

            foreach (var road in objectManager.GetAllEntities().OfType<RoadEntity>())
            {
                if (road != null
                    && !string.IsNullOrEmpty(road.id)
                    && road.controlPoints != null
                    && road.controlPoints.Count >= 2)
                {
                    roads[road.id] = new RoadGeometry(road.id, road.controlPoints);
                }
            }

            var lights = trafficService?.TrafficLights;
            for (int i = 0; lights != null && i < lights.Count; i++)
            {
                var light = lights[i];
                for (int j = 0; light?.controlledRoadIds != null && j < light.controlledRoadIds.Count; j++)
                {
                    if (roads.TryGetValue(light.controlledRoadIds[j], out var road))
                    {
                        road.AddEvent(road.Project(light.position, out _, out _), light.id);
                    }
                }
            }

            foreach (var road in roads.Values)
            {
                road.FinalizeEvents();
            }
        }

        public bool TryGetRouteFeatures(
            VehicleEntity vehicle,
            TrafficLightEntity light,
            Vector3 targetPosition,
            out float currentDistance,
            out float straightDistance,
            out float leftDistance,
            out float rightDistance,
            out float uturnDistance)
        {
            currentDistance = straightDistance = leftDistance =
                rightDistance = uturnDistance = float.PositiveInfinity;

            if (vehicle == null
                || light == null
                || string.IsNullOrEmpty(vehicle.currentRoadId)
                || !roads.TryGetValue(vehicle.currentRoadId, out var currentRoad))
            {
                return false;
            }

            var graph = GetTargetGraph(targetPosition);
            if (graph == null
                || !graph.TryGetEventIndex(vehicle.currentRoadId, light.id, out int eventIndex))
            {
                return false;
            }

            float vehicleProgress = currentRoad.Project(vehicle.position, out _, out Vector3 tangent);
            Vector3 forward = vehicle.rotation * Vector3.forward;
            forward.y = 0f;
            int direction = forward.sqrMagnitude <= 0.0001f || Vector3.Dot(forward.normalized, tangent) >= 0f ? 1 : -1;
            float lightProgress = currentRoad.Project(light.position, out _, out Vector3 lightTangent);
            float approach = direction > 0 ? lightProgress - vehicleProgress : vehicleProgress - lightProgress;
            if (approach < -MergeEpsilon)
            {
                return false;
            }
            approach = Mathf.Max(0f, approach);

            straightDistance = Add(approach, graph.ForcedDeparture(vehicle.currentRoadId, eventIndex, direction));
            Vector3 incoming = lightTangent * direction;
            leftDistance = TurnDistance(
                graph, light, vehicle.currentRoadId, incoming, VehicleDecisionAction.Left, approach);
            rightDistance = TurnDistance(
                graph, light, vehicle.currentRoadId, incoming, VehicleDecisionAction.Right, approach);
            // Atomic UTurn returns to the same road in the opposite direction.
            // Its graph prediction must therefore differ from a Left turn,
            // which departs onto the alternative road.
            uturnDistance = Add(
                approach + SimulationConfig.IntersectionGraphUTurnCostMeters,
                graph.ForcedDeparture(vehicle.currentRoadId, eventIndex, -direction));
            currentDistance = Mathf.Min(straightDistance, leftDistance, rightDistance, uturnDistance);
            return !float.IsPositiveInfinity(currentDistance);
        }

        float TurnDistance(
            TargetGraph graph,
            TrafficLightEntity light,
            string currentRoadId,
            Vector3 incoming,
            VehicleDecisionAction action,
            float approach)
        {
            if (!trafficService.TryGetAlternativeRoadId(light, currentRoadId, out string targetRoadId)
                || !roads.TryGetValue(targetRoadId, out var targetRoad)
                || !graph.TryGetEventIndex(targetRoadId, light.id, out int targetEventIndex))
            {
                return float.PositiveInfinity;
            }

            Vector3 desired = Quaternion.Euler(0f, ResolveExecutedTurnAngle(action), 0f) * incoming;
            targetRoad.Project(light.position, out _, out Vector3 targetForward);
            int targetDirection = Vector3.Dot(desired, targetForward) >= Vector3.Dot(desired, -targetForward) ? 1 : -1;
            return Add(approach, graph.ForcedDeparture(targetRoadId, targetEventIndex, targetDirection));
        }

        static float ResolveExecutedTurnAngle(VehicleDecisionAction action)
        {
            return action switch
            {
                VehicleDecisionAction.Right => 90f,
                VehicleDecisionAction.Left => -90f,
                VehicleDecisionAction.UTurn => 180f,
                _ => 0f,
            };
        }

        TargetGraph GetTargetGraph(Vector3 targetPosition)
        {
            string key = $"{Mathf.RoundToInt(targetPosition.x * 100f)}:{Mathf.RoundToInt(targetPosition.z * 100f)}";
            if (targetGraphs.TryGetValue(key, out var graph))
            {
                return graph;
            }

            RoadGeometry targetRoad = null;
            float targetProgress = 0f;
            float bestDistance = float.PositiveInfinity;
            foreach (var road in roads.Values.OrderBy(road => road.Id, StringComparer.Ordinal))
            {
                float progress = road.Project(targetPosition, out Vector3 projected, out _);
                projected.y = targetPosition.y;
                float distance = (projected - targetPosition).sqrMagnitude;
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    targetRoad = road;
                    targetProgress = progress;
                }
            }

            if (targetRoad == null)
            {
                return null;
            }

            graph = new TargetGraph(roads, trafficService, targetRoad.Id, targetProgress);
            targetGraphs[key] = graph;
            return graph;
        }

        static float Add(float a, float b)
        {
            return float.IsPositiveInfinity(a) || float.IsPositiveInfinity(b)
                ? float.PositiveInfinity
                : a + b;
        }

        sealed class TargetGraph
        {
            readonly Dictionary<string, RoadGeometry> roads;
            readonly Dictionary<Node, List<Edge>> edges = new();
            readonly Dictionary<Node, float> distances = new();
            readonly Dictionary<string, Dictionary<string, int>> lightIndices = new();
            readonly HashSet<Node> targets = new();

            public TargetGraph(
                Dictionary<string, RoadGeometry> source,
                TrafficService trafficService,
                string targetRoadId,
                float targetProgress)
            {
                roads = source.ToDictionary(pair => pair.Key, pair => pair.Value.Clone());
                roads[targetRoadId].AddEvent(targetProgress, "__target__");
                foreach (var road in roads.Values)
                {
                    road.FinalizeEvents();
                    BuildRoadEdges(road);
                }
                BuildIntersectionEdges(trafficService);
                BuildLookups();
                RunReverseDijkstra();
            }

            public bool TryGetEventIndex(string roadId, string lightId, out int index)
            {
                index = -1;
                return lightIndices.TryGetValue(roadId, out var byLight)
                    && byLight.TryGetValue(lightId, out index);
            }

            public float ForcedDeparture(string roadId, int eventIndex, int direction)
            {
                var current = new Node(roadId, eventIndex, direction);
                if (targets.Contains(current))
                {
                    return 0f;
                }

                var road = roads[roadId];
                int next = eventIndex + (direction > 0 ? 1 : -1);
                if (next >= 0 && next < road.Events.Count)
                {
                    float cost = Mathf.Abs(road.Events[next].Progress - road.Events[eventIndex].Progress);
                    return Add(cost, Distance(new Node(roadId, next, direction)));
                }

                return Add(
                    SimulationConfig.IntersectionGraphEndpointTurnCostMeters,
                    Distance(new Node(roadId, eventIndex, -direction)));
            }

            void BuildRoadEdges(RoadGeometry road)
            {
                for (int i = 0; i < road.Events.Count; i++)
                {
                    AddNode(new Node(road.Id, i, 1));
                    AddNode(new Node(road.Id, i, -1));
                }
                for (int i = 0; i + 1 < road.Events.Count; i++)
                {
                    float cost = road.Events[i + 1].Progress - road.Events[i].Progress;
                    AddEdge(new Node(road.Id, i, 1), new Node(road.Id, i + 1, 1), cost);
                    AddEdge(new Node(road.Id, i + 1, -1), new Node(road.Id, i, -1), cost);
                }

                int last = road.Events.Count - 1;
                AddEdge(new Node(road.Id, 0, -1), new Node(road.Id, 0, 1),
                    SimulationConfig.IntersectionGraphEndpointTurnCostMeters);
                AddEdge(new Node(road.Id, last, 1), new Node(road.Id, last, -1),
                    SimulationConfig.IntersectionGraphEndpointTurnCostMeters);
            }

            void BuildIntersectionEdges(TrafficService trafficService)
            {
                var lights = trafficService?.TrafficLights;
                for (int i = 0; lights != null && i < lights.Count; i++)
                {
                    var light = lights[i];
                    if (light?.controlledRoadIds == null)
                    {
                        continue;
                    }

                    foreach (string sourceId in light.controlledRoadIds)
                    foreach (string targetId in light.controlledRoadIds)
                    {
                        if (sourceId == targetId
                            || !roads.TryGetValue(sourceId, out var sourceRoad)
                            || !roads.TryGetValue(targetId, out var targetRoad)
                            || !sourceRoad.TryGetEventIndex(light.id, out int sourceEvent)
                            || !targetRoad.TryGetEventIndex(light.id, out int targetEvent))
                        {
                            continue;
                        }

                        for (int direction = -1; direction <= 1; direction += 2)
                        {
                            Vector3 incoming = sourceRoad.TangentAtEvent(sourceEvent) * direction;
                            AddTurn(sourceId, sourceEvent, direction, targetRoad, targetEvent, incoming, -90f);
                            AddTurn(sourceId, sourceEvent, direction, targetRoad, targetEvent, incoming, 90f);
                        }
                    }
                }
            }

            void AddTurn(
                string sourceRoadId,
                int sourceEvent,
                int sourceDirection,
                RoadGeometry targetRoad,
                int targetEvent,
                Vector3 incoming,
                float angle)
            {
                Vector3 desired = Quaternion.Euler(0f, angle, 0f) * incoming;
                Vector3 targetForward = targetRoad.TangentAtEvent(targetEvent);
                int targetDirection = Vector3.Dot(desired, targetForward) >= Vector3.Dot(desired, -targetForward) ? 1 : -1;
                AddEdge(
                    new Node(sourceRoadId, sourceEvent, sourceDirection),
                    new Node(targetRoad.Id, targetEvent, targetDirection),
                    SimulationConfig.IntersectionGraphTurnCostMeters);
            }

            void BuildLookups()
            {
                foreach (var road in roads.Values)
                {
                    var byLight = new Dictionary<string, int>();
                    for (int i = 0; i < road.Events.Count; i++)
                    {
                        foreach (string id in road.Events[i].Ids)
                        {
                            if (id == "__target__")
                            {
                                targets.Add(new Node(road.Id, i, 1));
                                targets.Add(new Node(road.Id, i, -1));
                            }
                            else if (!id.StartsWith("__", StringComparison.Ordinal))
                            {
                                byLight[id] = i;
                            }
                        }
                    }
                    lightIndices[road.Id] = byLight;
                }
            }

            void RunReverseDijkstra()
            {
                var reverse = new Dictionary<Node, List<Edge>>();
                foreach (var pair in edges)
                foreach (var edge in pair.Value)
                {
                    if (!reverse.TryGetValue(edge.To, out var incoming))
                    {
                        incoming = new List<Edge>();
                        reverse[edge.To] = incoming;
                    }
                    incoming.Add(new Edge(pair.Key, edge.Cost));
                }

                var queue = targets.Select(target => (node: target, distance: 0f)).ToList();
                foreach (var target in targets)
                {
                    distances[target] = 0f;
                }

                while (queue.Count > 0)
                {
                    int best = 0;
                    for (int i = 1; i < queue.Count; i++)
                    {
                        if (queue[i].distance < queue[best].distance) best = i;
                    }
                    var current = queue[best];
                    queue.RemoveAt(best);
                    if (current.distance > Distance(current.node) + 0.0001f
                        || !reverse.TryGetValue(current.node, out var incoming))
                    {
                        continue;
                    }

                    foreach (var edge in incoming)
                    {
                        float candidate = current.distance + edge.Cost;
                        if (candidate + 0.0001f < Distance(edge.To))
                        {
                            distances[edge.To] = candidate;
                            queue.Add((edge.To, candidate));
                        }
                    }
                }
            }

            float Distance(Node node)
            {
                return distances.TryGetValue(node, out float value) ? value : float.PositiveInfinity;
            }

            void AddNode(Node node)
            {
                if (!edges.ContainsKey(node)) edges[node] = new List<Edge>();
            }

            void AddEdge(Node from, Node to, float cost)
            {
                AddNode(from);
                AddNode(to);
                edges[from].Add(new Edge(to, Mathf.Max(0f, cost)));
            }
        }

        sealed class RoadGeometry
        {
            readonly List<Vector3> points = new();
            readonly List<float> cumulative = new();
            readonly List<RoadEvent> pending = new();
            readonly Dictionary<string, int> indexById = new();

            public RoadGeometry(string id, IReadOnlyList<Vector3> source)
            {
                Id = id;
                for (int i = 0; source != null && i < source.Count; i++)
                {
                    Vector3 point = source[i];
                    point.y = 0f;
                    if (points.Count == 0 || (points[points.Count - 1] - point).sqrMagnitude > 0.0001f)
                    {
                        points.Add(point);
                    }
                }
                cumulative.Add(0f);
                for (int i = 1; i < points.Count; i++)
                {
                    cumulative.Add(cumulative[i - 1] + Vector3.Distance(points[i - 1], points[i]));
                }
                AddEvent(0f, "__start__");
                AddEvent(Length, "__end__");
            }

            public string Id { get; }
            public float Length => cumulative[cumulative.Count - 1];
            public List<RoadEvent> Events { get; } = new();

            public void AddEvent(float progress, string id)
            {
                pending.Add(new RoadEvent(Mathf.Clamp(progress, 0f, Length), id));
            }

            public void FinalizeEvents()
            {
                Events.Clear();
                indexById.Clear();
                pending.Sort((a, b) => a.Progress.CompareTo(b.Progress));
                foreach (var candidate in pending)
                {
                    if (Events.Count > 0
                        && Mathf.Abs(Events[Events.Count - 1].Progress - candidate.Progress) <= MergeEpsilon)
                    {
                        Events[Events.Count - 1].Merge(candidate);
                    }
                    else
                    {
                        Events.Add(candidate.Clone());
                    }
                }
                for (int i = 0; i < Events.Count; i++)
                foreach (string id in Events[i].Ids)
                {
                    indexById[id] = i;
                }
            }

            public bool TryGetEventIndex(string id, out int index)
            {
                return indexById.TryGetValue(id, out index);
            }

            public Vector3 TangentAtEvent(int eventIndex)
            {
                PointAt(Events[eventIndex].Progress, out Vector3 tangent);
                return tangent;
            }

            public float Project(Vector3 position, out Vector3 projected, out Vector3 tangent)
            {
                position.y = 0f;
                projected = points[0];
                tangent = Vector3.forward;
                float best = float.PositiveInfinity;
                float progress = 0f;
                for (int i = 0; i + 1 < points.Count; i++)
                {
                    Vector3 segment = points[i + 1] - points[i];
                    float lengthSquared = segment.sqrMagnitude;
                    if (lengthSquared <= 0.0001f) continue;
                    float t = Mathf.Clamp01(Vector3.Dot(position - points[i], segment) / lengthSquared);
                    Vector3 candidate = points[i] + segment * t;
                    float distance = (position - candidate).sqrMagnitude;
                    if (distance < best)
                    {
                        best = distance;
                        projected = candidate;
                        tangent = segment.normalized;
                        progress = cumulative[i] + Mathf.Sqrt(lengthSquared) * t;
                    }
                }
                return progress;
            }

            public RoadGeometry Clone()
            {
                var clone = new RoadGeometry(Id, points);
                clone.pending.Clear();
                foreach (var item in pending) clone.pending.Add(item.Clone());
                clone.FinalizeEvents();
                return clone;
            }

            Vector3 PointAt(float progress, out Vector3 tangent)
            {
                progress = Mathf.Clamp(progress, 0f, Length);
                for (int i = 0; i + 1 < points.Count; i++)
                {
                    if (progress > cumulative[i + 1] && i + 2 < points.Count) continue;
                    Vector3 segment = points[i + 1] - points[i];
                    float length = segment.magnitude;
                    tangent = length > 0.0001f ? segment / length : Vector3.forward;
                    float t = length > 0.0001f ? (progress - cumulative[i]) / length : 0f;
                    return points[i] + segment * Mathf.Clamp01(t);
                }
                tangent = Vector3.forward;
                return points[points.Count - 1];
            }
        }

        sealed class RoadEvent
        {
            public RoadEvent(float progress, string id)
            {
                Progress = progress;
                Ids.Add(id);
            }

            public float Progress { get; }
            public List<string> Ids { get; } = new();

            public void Merge(RoadEvent other)
            {
                foreach (string id in other.Ids)
                {
                    if (!Ids.Contains(id)) Ids.Add(id);
                }
            }

            public RoadEvent Clone()
            {
                var clone = new RoadEvent(Progress, Ids[0]);
                for (int i = 1; i < Ids.Count; i++) clone.Ids.Add(Ids[i]);
                return clone;
            }
        }

        readonly struct Node : IEquatable<Node>
        {
            public Node(string roadId, int eventIndex, int direction)
            {
                RoadId = roadId;
                EventIndex = eventIndex;
                Direction = direction >= 0 ? 1 : -1;
            }
            public string RoadId { get; }
            public int EventIndex { get; }
            public int Direction { get; }
            public bool Equals(Node other) => RoadId == other.RoadId
                && EventIndex == other.EventIndex && Direction == other.Direction;
            public override bool Equals(object obj) => obj is Node other && Equals(other);
            public override int GetHashCode()
            {
                unchecked
                {
                    int hash = RoadId != null ? RoadId.GetHashCode() : 0;
                    return ((hash * 397) ^ EventIndex) * 397 ^ Direction;
                }
            }
        }

        readonly struct Edge
        {
            public Edge(Node to, float cost)
            {
                To = to;
                Cost = cost;
            }
            public Node To { get; }
            public float Cost { get; }
        }
    }
}
