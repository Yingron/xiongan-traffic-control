using UnityEngine;

namespace CitySimulation.Presentation
{
    /// <summary>Applies an inexpensive asphalt / lane-marking treatment to generated road LineRenderers.</summary>
    public static class RoadPresentationStyler
    {
        static Material _asphalt;
        static Material _marking;

        public static void ApplyToGeneratedRoads()
        {
            foreach (var road in Object.FindObjectsOfType<LineRenderer>(true))
            {
                if (road.gameObject.name != "section" || road.positionCount < 2) continue;
                road.widthMultiplier = 12f;
                road.numCornerVertices = 2;
                road.numCapVertices = 2;
                road.sharedMaterial = AsphaltMaterial;
                if (road.transform.Find("PresentationMarkings") == null)
                    CreateMarkings(road);
            }
        }

        static void CreateMarkings(LineRenderer road)
        {
            var count = road.positionCount;
            var points = new Vector3[count];
            road.GetPositions(points);
            var left = new Vector3[count];
            var right = new Vector3[count];
            for (var i = 0; i < count; i++)
            {
                var before = points[Mathf.Max(0, i - 1)];
                var after = points[Mathf.Min(count - 1, i + 1)];
                var tangent = (after - before); tangent.y = 0f;
                if (tangent.sqrMagnitude < 0.001f) tangent = Vector3.forward;
                var side = Vector3.Cross(Vector3.up, tangent.normalized) * 5.55f;
                left[i] = points[i] + side + Vector3.up * 0.035f;
                right[i] = points[i] - side + Vector3.up * 0.035f;
            }

            var parent = new GameObject("PresentationMarkings").transform;
            parent.SetParent(road.transform, true);
            CreateSolidLine(parent, "EdgeLeft", left);
            CreateSolidLine(parent, "EdgeRight", right);

            for (var segment = 0; segment < count - 1; segment++)
            {
                var start = points[segment]; var end = points[segment + 1];
                var delta = end - start; delta.y = 0f;
                var length = delta.magnitude;
                if (length < 0.1f) continue;
                var direction = delta / length;
                for (var distance = 8f; distance < length - 2f; distance += 18f)
                    CreateDash(parent, start + direction * distance + Vector3.up * 0.045f, direction);
            }
        }

        static void CreateSolidLine(Transform parent, string name, Vector3[] points)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, true);
            var line = go.AddComponent<LineRenderer>();
            line.useWorldSpace = true;
            line.positionCount = points.Length;
            line.SetPositions(points);
            line.widthMultiplier = 0.22f;
            line.numCornerVertices = 1;
            line.sharedMaterial = MarkingMaterial;
            line.startColor = line.endColor = new Color(0.96f, 0.91f, 0.68f);
        }

        static void CreateDash(Transform parent, Vector3 position, Vector3 direction)
        {
            var dash = GameObject.CreatePrimitive(PrimitiveType.Cube);
            dash.name = "CenterDash";
            dash.transform.SetParent(parent, true);
            dash.transform.position = position;
            dash.transform.rotation = Quaternion.LookRotation(direction, Vector3.up);
            dash.transform.localScale = new Vector3(0.28f, 0.04f, 7f);
            dash.GetComponent<Renderer>().sharedMaterial = MarkingMaterial;
            var collider = dash.GetComponent<Collider>();
            if (collider != null) Object.Destroy(collider);
        }

        static Material AsphaltMaterial
        {
            get
            {
                if (_asphalt == null)
                {
                    _asphalt = new Material(Shader.Find("Standard")) { name = "Runtime_Asphalt" };
                    _asphalt.color = new Color(0.075f, 0.095f, 0.12f);
                    _asphalt.SetFloat("_Glossiness", 0.22f);
                }
                return _asphalt;
            }
        }

        static Material MarkingMaterial
        {
            get
            {
                if (_marking == null)
                {
                    _marking = new Material(Shader.Find("Standard")) { name = "Runtime_RoadMarking" };
                    _marking.color = new Color(0.96f, 0.91f, 0.68f);
                    _marking.SetFloat("_Glossiness", 0.35f);
                }
                return _marking;
            }
        }
    }
}
