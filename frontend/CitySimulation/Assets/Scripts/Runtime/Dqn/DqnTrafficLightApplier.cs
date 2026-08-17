using System.Collections.Generic;
using CitySimulation.GameObjects.Entities;
using UnityEngine;

namespace CitySimulation.Runtime.Dqn
{
    /// <summary>Reflects the phase confirmed by the API-controlled SUMO session in Unity signal visuals.</summary>
    [RequireComponent(typeof(DqnControlClient))]
    [DisallowMultipleComponent]
    public class DqnTrafficLightApplier : MonoBehaviour
    {
        DqnControlClient _client;
        readonly Dictionary<string, TrafficLightAnimator> _signals = new Dictionary<string, TrafficLightAnimator>();

        void Start()
        {
            _client = GetComponent<DqnControlClient>();
            _client.OnStateUpdated += Apply;
        }

        void OnDestroy()
        {
            if (_client != null) _client.OnStateUpdated -= Apply;
        }

        void Apply(ApiStateSnapshot state)
        {
            if (state?.intersections == null) return;
            if (_signals.Count == 0) BuildLookup();
            foreach (var item in state.intersections)
            {
                if (item == null || string.IsNullOrEmpty(item.id) || !_signals.TryGetValue(item.id, out var signal)) continue;
                signal.greenDuration = 9999f;
                signal.yellowDuration = 9999f;
                // The visual animator has NS/EW primary phases.  Both straight
                // and left-turn API phases map to their corresponding direction.
                signal.SetPhase(item.phase < 2 ? 0 : 2);
            }
        }

        void BuildLookup()
        {
            foreach (var signal in FindObjectsOfType<TrafficLightAnimator>())
            {
                foreach (var id in ExpectedIds())
                {
                    if (signal.name.Contains(id)) { _signals[id] = signal; break; }
                }
            }
            // Imported anchors can retain generic prefab names.  Complete the
            // mapping with the same geometry used by the SUMO visualization
            // bridge so every one of the 30 signals receives its API phase.
            if (_signals.Count < 30) MatchRemainingSignalsByPosition();
            Debug.Log($"[DqnControl] Unity 信号灯联动：已匹配 {_signals.Count}/30 个路口。");
        }

        void MatchRemainingSignalsByPosition()
        {
            var positions = new[]
            {
                new Vector2(600,1000), new Vector2(800,800), new Vector2(800,1000), new Vector2(200,800), new Vector2(0,1000),
                new Vector2(400,800), new Vector2(200,1000), new Vector2(600,800), new Vector2(200,600), new Vector2(400,1000),
                new Vector2(400,600), new Vector2(600,600), new Vector2(0,0), new Vector2(0,800), new Vector2(800,600),
                new Vector2(0,400), new Vector2(0,600), new Vector2(200,400), new Vector2(400,400), new Vector2(600,400),
                new Vector2(800,400), new Vector2(0,200), new Vector2(200,200), new Vector2(400,200), new Vector2(600,200),
                new Vector2(200,0), new Vector2(400,0), new Vector2(800,200), new Vector2(600,0), new Vector2(800,0),
            };
            foreach (var signal in FindObjectsOfType<TrafficLightAnimator>())
            {
                var point = new Vector2(signal.transform.position.x, signal.transform.position.z);
                var closest = -1;
                var closestDistance = 50f;
                for (var index = 0; index < positions.Length; index++)
                {
                    if (_signals.ContainsKey($"J{index + 1:00}")) continue;
                    var distance = Vector2.Distance(point, positions[index]);
                    if (distance < closestDistance) { closest = index; closestDistance = distance; }
                }
                if (closest >= 0) _signals[$"J{closest + 1:00}"] = signal;
            }
        }

        static IEnumerable<string> ExpectedIds()
        {
            for (var index = 1; index <= 30; index++) yield return $"J{index:00}";
        }
    }
}
