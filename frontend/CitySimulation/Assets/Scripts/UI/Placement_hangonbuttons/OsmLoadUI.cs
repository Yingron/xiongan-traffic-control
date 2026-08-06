using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Xml.Linq;
using CitySimulation.DTO;
using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;
using CitySimulation.GameObjects;

namespace CitySimulation.UI.Placement_hangonbuttons
{
    /// <summary>
    /// Binds the osm_load button to import buildings from an OSM XML file.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public class OsmLoadUI : MonoBehaviour
    {
        private const string OsmLoadButtonName = "osm_load";

        private ObjectManager _objectManager;
        private Button _osmLoadButton;

        private void OnEnable()
        {
            _objectManager = GameServices.ObjectManager;
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _osmLoadButton = root?.Q<Button>(OsmLoadButtonName);
            if (_osmLoadButton == null)
            {
                Debug.LogWarning("[OsmLoadUI] Button 'osm_load' not found in UXML.");
                return;
            }
            _osmLoadButton.clicked += OnOsmLoadClicked;
        }

        private void OnDisable()
        {
            if (_osmLoadButton != null)
            {
                _osmLoadButton.clicked -= OnOsmLoadClicked;
            }
        }

        private void OnOsmLoadClicked()
        {
#if UNITY_EDITOR
            string picked = UnityEditor.EditorUtility.OpenFilePanel(
                "Select OSM File",
                Path.Combine(Application.dataPath, "Scripts", "Maps"),
                "osm,xml");
            if (string.IsNullOrEmpty(picked) || !File.Exists(picked))
            {
                return;
            }

            try
            {
                int buildings = ImportFromOsm(picked);
                Debug.Log($"[OsmLoadUI] OSM imported: buildings={buildings}");
            }
            catch (Exception e)
            {
                Debug.LogError($"[OsmLoadUI] Failed to import OSM: {e.Message}");
            }
#else
            Debug.LogWarning("[OsmLoadUI] File picker not available at runtime without plugin.");
#endif
        }

        private int ImportFromOsm(string osmPath)
        {
            if (_objectManager == null)
            {
                Debug.LogError("[OsmLoadUI] ObjectManager not available.");
                return 0;
            }

            var doc = XDocument.Load(osmPath);
            var nodes = new Dictionary<long, (double lat, double lon)>();

            var buildings = new List<BuildingInfo>();
            double allMinX = double.PositiveInfinity;
            double allMaxX = double.NegativeInfinity;
            double allMinZ = double.PositiveInfinity;
            double allMaxZ = double.NegativeInfinity;

            foreach (var n in doc.Root.Elements("node"))
            {
                if (!long.TryParse(n.Attribute("id")?.Value, out var id)) continue;
                if (!double.TryParse(n.Attribute("lat")?.Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var lat)) continue;
                if (!double.TryParse(n.Attribute("lon")?.Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var lon)) continue;
                nodes[id] = (lat, lon);
            }

            if (nodes.Count == 0)
            {
                return 0;
            }

            var firstNode = default((double lat, double lon));
            foreach (var value in nodes.Values)
            {
                firstNode = value;
                break;
            }
            double originLat = firstNode.lat;
            double originLon = firstNode.lon;

            foreach (var way in doc.Root.Elements("way"))
            {
                bool isBuilding = false;
                string heightTag = null;
                string levelsTag = null;
                float rotationDeg = 0f;

                foreach (var tag in way.Elements("tag"))
                {
                    var k = tag.Attribute("k")?.Value;
                    var v = tag.Attribute("v")?.Value;
                    if (string.Equals(k, "building", StringComparison.OrdinalIgnoreCase))
                    {
                        isBuilding = true;
                    }
                    else if (string.Equals(k, "height", StringComparison.OrdinalIgnoreCase))
                    {
                        heightTag = v;
                    }
                    else if (string.Equals(k, "building:levels", StringComparison.OrdinalIgnoreCase))
                    {
                        levelsTag = v;
                    }
                }

                var pts = new List<(double lat, double lon)>();
                foreach (var nd in way.Elements("nd"))
                {
                    if (!long.TryParse(nd.Attribute("ref")?.Value, out var refId)) continue;
                    if (nodes.TryGetValue(refId, out var latlon))
                    {
                        pts.Add(latlon);
                    }
                }

                if (!isBuilding || pts.Count < 3)
                {
                    continue;
                }

                var localPoints = ConvertToLocalPoints(
                    pts,
                    originLat,
                    originLon,
                    out var minX,
                    out var maxX,
                    out var minZ,
                    out var maxZ,
                    out var cx,
                    out var cz);

                float height = ResolveHeightMeters(heightTag, levelsTag);
                if (height < 1f) height = 6f;

                float width = Mathf.Max(1f, (float)(maxX - minX));
                float length = Mathf.Max(1f, (float)(maxZ - minZ));
                rotationDeg = ComputeRotationFromFootprint(localPoints);

                buildings.Add(new BuildingInfo
                {
                    centerX = cx,
                    centerZ = cz,
                    width = width,
                    length = length,
                    height = height,
                    rotationDeg = rotationDeg,
                    minX = minX,
                    maxX = maxX,
                    minZ = minZ,
                    maxZ = maxZ
                });

                UpdateBounds(minX, minZ, ref allMinX, ref allMaxX, ref allMinZ, ref allMaxZ);
                UpdateBounds(maxX, maxZ, ref allMinX, ref allMaxX, ref allMinZ, ref allMaxZ);
            }

            if (buildings.Count == 0)
            {
                return 0;
            }

            GetTargetArea(out var targetCenter, out var targetSize, out var baseY);
            double srcSizeX = Math.Max(1.0, allMaxX - allMinX);
            double srcSizeZ = Math.Max(1.0, allMaxZ - allMinZ);
            double srcCenterX = (allMinX + allMaxX) * 0.5;
            double srcCenterZ = (allMinZ + allMaxZ) * 0.5;
            float scale = (float)Math.Min(targetSize.x / srcSizeX, targetSize.z / srcSizeZ);

            int createdBuildings = 0;
            foreach (var b in buildings)
            {
                float scaledWidth = Mathf.Max(0.1f, b.width * scale);
                float scaledLength = Mathf.Max(0.1f, b.length * scale);
                float scaledHeight = Mathf.Max(0.1f, b.height * scale);

                float x = (float)((b.centerX - srcCenterX) * scale + targetCenter.x);
                float z = (float)((b.centerZ - srcCenterZ) * scale + targetCenter.z);
                float y = baseY + scaledHeight * 0.5f;

                var dto = new BuildingDTO
                {
                    id = Guid.NewGuid().ToString(),
                    category = MapCategory.Building,
                    styleId = null,
                    position = new Vector3(x, y, z),
                    rotation = Quaternion.Euler(0f, b.rotationDeg, 0f),
                    size = new Vector3(scaledWidth, scaledHeight, scaledLength)
                };

                var entity = _objectManager.CreateObject(dto, need_validate: false);
                if (entity?.gameObject != null)
                {
                    createdBuildings++;
                }
            }

            return createdBuildings;
        }

        private static void GetTargetArea(out Vector3 center, out Vector3 size, out float baseY)
        {
            const float fallbackSize = 100f;
            var plane = GameObject.Find("Plane");
            if (plane != null)
            {
                var renderer = plane.GetComponent<Renderer>();
                if (renderer != null)
                {
                    var bounds = renderer.bounds;
                    center = bounds.center;
                    size = bounds.size;
                    baseY = bounds.max.y;
                    Debug.Log($"[OsmLoadUI] Plane bounds size={size}, center={center}");
                    return;
                }
            }

            center = Vector3.zero;
            size = new Vector3(fallbackSize, 0f, fallbackSize);
            baseY = 0f;
            Debug.LogWarning("[OsmLoadUI] Plane not found; using 100x100 fallback area at origin.");
        }

        private struct BuildingInfo
        {
            public double centerX;
            public double centerZ;
            public float width;
            public float length;
            public float height;
            public float rotationDeg;
            public double minX;
            public double maxX;
            public double minZ;
            public double maxZ;
        }

        private static void UpdateBounds(
            double x,
            double z,
            ref double minX,
            ref double maxX,
            ref double minZ,
            ref double maxZ)
        {
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (z < minZ) minZ = z;
            if (z > maxZ) maxZ = z;
        }

        private static float ResolveHeightMeters(string heightTag, string levelsTag)
        {
            if (!string.IsNullOrEmpty(heightTag))
            {
                var cleaned = heightTag.Trim().ToLowerInvariant().Replace("m", "");
                if (float.TryParse(cleaned, NumberStyles.Float, CultureInfo.InvariantCulture, out var h))
                {
                    return h;
                }
            }

            if (!string.IsNullOrEmpty(levelsTag))
            {
                if (float.TryParse(levelsTag, NumberStyles.Float, CultureInfo.InvariantCulture, out var levels))
                {
                    return levels * 3.5f;
                }
            }

            return 0f;
        }

        private static List<Vector2> ConvertToLocalPoints(
            List<(double lat, double lon)> pts,
            double originLat,
            double originLon,
            out double minX,
            out double maxX,
            out double minZ,
            out double maxZ,
            out double centerX,
            out double centerZ)
        {
            const double R = 6378137.0;
            double lat0 = originLat * Math.PI / 180.0;
            minX = double.PositiveInfinity;
            maxX = double.NegativeInfinity;
            minZ = double.PositiveInfinity;
            maxZ = double.NegativeInfinity;
            var localPoints = new List<Vector2>(pts.Count);

            foreach (var p in pts)
            {
                double lat = p.lat * Math.PI / 180.0;
                double lon = p.lon * Math.PI / 180.0;
                double dLat = lat - lat0;
                double dLon = lon - (originLon * Math.PI / 180.0);
                double x = dLon * Math.Cos(lat0) * R;
                double z = dLat * R;
                localPoints.Add(new Vector2((float)x, (float)z));
                if (x < minX) minX = x;
                if (x > maxX) maxX = x;
                if (z < minZ) minZ = z;
                if (z > maxZ) maxZ = z;
            }

            centerX = (minX + maxX) * 0.5;
            centerZ = (minZ + maxZ) * 0.5;
            return localPoints;
        }

        private static float ComputeRotationFromFootprint(List<Vector2> points)
        {
            if (points == null || points.Count < 2)
            {
                return 0f;
            }

            float maxLenSq = 0f;
            Vector2 bestDir = Vector2.up;
            for (int i = 0; i < points.Count; i++)
            {
                int j = (i + 1) % points.Count;
                var dir = points[j] - points[i];
                float lenSq = dir.sqrMagnitude;
                if (lenSq > maxLenSq)
                {
                    maxLenSq = lenSq;
                    bestDir = dir;
                }
            }

            if (maxLenSq < 0.000001f)
            {
                return 0f;
            }

            // Yaw angle in Unity: 0 deg is +Z, positive rotates toward +X.
            float angleDeg = Mathf.Atan2(bestDir.x, bestDir.y) * Mathf.Rad2Deg;
            return angleDeg;
        }
    }
}
