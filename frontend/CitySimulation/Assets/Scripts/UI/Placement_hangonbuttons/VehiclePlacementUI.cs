using System;
using System.Collections.Generic;
using CitySimulation.DTO;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.Placement_hangonbuttons
{
    /// <summary>
    /// Vehicle placement tool: snap to nearest road segment, auto lane side & forward direction (right-hand traffic).
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public class VehiclePlacementUI : MonoBehaviour
    {
        [Serializable]
        private struct ButtonStyleMapping
        {
            public string buttonName;
            public string styleId;
            public VehicleType vehicleType;
        }

        // Single source of truth for vehicle buttons; no inspector overrides required.
        private readonly ButtonStyleMapping[] mappings =
        {
            new ButtonStyleMapping { buttonName = "createVehicle_Truck_color03", styleId = "Truck_color03", vehicleType = VehicleType.Normal },
            new ButtonStyleMapping { buttonName = "createVehicle_Police", styleId = "Police", vehicleType = VehicleType.Emergency }
        };

        [SerializeField] private float previewAlpha = 0.6f;
        [SerializeField] private float snapRadius = 4f; // world units within which snapping to road is valid

        private string _currentStyleId;
        private VehicleType _currentVehicleType;

        private ObjectManager _objectManager;
        private PrefabFactory _factory;
        private VehicleEntity _previewEntity;
        private bool _placementMode;
        private readonly List<Renderer> _previewRenderers = new();
        private MaterialPropertyBlock _mpb;
        private readonly List<(Button button, Action handler)> _registeredHandlers = new();

        private void Awake()
        {
            _factory = GameServices.Prefabs;
            _objectManager = GameServices.ObjectManager;
        }

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui.rootVisualElement;

            if (mappings == null || mappings.Length == 0)
            {
                Debug.LogWarning("[VehiclePlacementUI] No button/style mappings configured.");
                return;
            }

            _currentStyleId = mappings[0].styleId; // default
            _currentVehicleType = mappings[0].vehicleType;

            foreach (var mapping in mappings)
            {
                RegisterButton(root, mapping.buttonName, mapping.styleId, mapping.vehicleType);
            }
        }

        private void OnDisable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            foreach (var entry in _registeredHandlers)
            {
                if (entry.button != null)
                {
                    entry.button.clicked -= entry.handler;
                }
            }
            _registeredHandlers.Clear();
            HidePreview();
        }

        private void RegisterButton(VisualElement root, string targetButtonName, string targetStyleId, VehicleType vehicleType)
        {
            if (string.IsNullOrEmpty(targetButtonName))
            {
                return;
            }

            var button = root?.Q<Button>(targetButtonName);
            if (button == null)
            {
                Debug.LogWarning($"[VehiclePlacementUI] Button '{targetButtonName}' not found.");
                return;
            }

            void Handler()
            {
                BeginPlacementForStyle(targetStyleId, vehicleType);
            }

            button.clicked += Handler;
            _registeredHandlers.Add((button, Handler));
        }

        private void BeginPlacementForStyle(string targetStyleId, VehicleType vehicleType)
        {
            _currentStyleId = targetStyleId;
            _previewEntity = null;
            HidePreview();
            _currentVehicleType = vehicleType;
            if (!_placementMode)
            {
                TogglePlacementMode();
            }
            else
            {
                EnsurePreview();
            }
        }

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.Escape) && _placementMode)
            {
                TogglePlacementMode();
                return;
            }

            if (!_placementMode)
            {
                return;
            }

            if (_previewEntity == null)
            {
                EnsurePreview();
            }

            if (!TryGetMouseGround(out var mousePos))
            {
                return;
            }

            // snap to nearest road
            // out params:
            //  - snappedLaneRight: unit vector pointing to the lane's right side (world XZ plane)
            //  - snappedTangent: forward direction along the lane (unit vector)
            if (TrySnapToRoad(mousePos, out var snappedPos, out var snappedRot, out var snappedLaneRight, out var snappedTangent, out var snappedRoadId))
            {
                _previewEntity.ApplyTransform(snappedPos, snappedRot);

                bool valid = _previewEntity.Validate(_objectManager).IsValid;

                SetPreviewColor(valid);
                if (valid && Input.GetMouseButtonDown(0))
                {
                    PlaceVehicle(snappedPos, snappedRot, snappedRoadId);
                }
            }
            else
            {
                // show invalid preview at mouse ground position
                _previewEntity.ApplyTransform(mousePos, Quaternion.identity);
                SetPreviewColor(false);
            }
        }

        private void TogglePlacementMode()
        {
            _placementMode = !_placementMode;
            if (_placementMode)
            {
                EnsurePreview();
            }
            else
            {
                HidePreview();
            }
        }

        private void EnsurePreview()
        {
            if (_previewEntity != null && _previewEntity.gameObject != null)
            {
                _previewEntity.gameObject.SetActive(true);
                return;
            }

            var dto = new VehicleDTO
            {
                id = "__preview_vehicle",
                category = MapCategory.Vehicle,
                styleId = _currentStyleId,
                position = Vector3.zero,
                rotation = Quaternion.identity,
                vehicleType = _currentVehicleType
            };
            _previewEntity = _factory.CreateEntity(dto) as VehicleEntity;
            if (_previewEntity?.gameObject != null)
            {
                CachePreviewRenderers(_previewEntity.gameObject);
                SetPreviewColor(false);
            }
        }

        private void HidePreview()
        {
            if (_previewEntity?.gameObject != null)
            {
                _previewEntity.gameObject.SetActive(false);
            }
        }

        private void PlaceVehicle(Vector3 pos, Quaternion rot, string currentRoadId)
        {
            var dto = new VehicleDTO
            {
                id = Guid.NewGuid().ToString(),
                category = MapCategory.Vehicle,
                styleId = _currentStyleId,
                position = pos,
                rotation = rot,
                vehicleType = _currentVehicleType,
                currentRoadId = currentRoadId
            };
            var entity = _objectManager.CreateObject(dto) as VehicleEntity;
            if (entity != null)
            {
                Debug.Log($"[VehiclePlacementUI] Placed vehicle {entity.id} at {pos} facing {rot.eulerAngles}.");
            }
        }

        private bool TrySnapToRoad(Vector3 mousePos, out Vector3 snappedPos, out Quaternion snappedRot, out Vector3 laneRight, out Vector3 laneTangent, out string roadId)
        {
            snappedPos = mousePos;
            snappedRot = Quaternion.identity;
            laneRight = Vector3.right;
            laneTangent = Vector3.forward;
            roadId = null;

            RoadEntity bestRoad = null;
            float bestDist = float.PositiveInfinity;
            Vector3 bestProj = Vector3.zero;
            Vector3 bestTangent = Vector3.forward;

            foreach (var entity in _objectManager.GetAllEntities())
            {
                if (entity is not RoadEntity road || road.controlPoints == null || road.controlPoints.Count < 2)
                {
                    continue;
                }

                for (int i = 0; i < road.controlPoints.Count - 1; i++)
                {
                    var a = road.controlPoints[i];
                    var b = road.controlPoints[i + 1];
                    var seg = b - a;
                    var segSqr = seg.sqrMagnitude;
                    if (segSqr < 0.0001f)
                    {
                        continue;
                    }
                    float t = Mathf.Clamp01(Vector3.Dot(mousePos - a, seg) / segSqr);
                    var proj = a + seg * t;
                    float dist = Vector3.Distance(mousePos, proj);
                    if (dist < bestDist)
                    {
                        bestDist = dist;
                        bestProj = proj;
                        bestTangent = seg.normalized;
                        bestRoad = road;
                    }
                }
            }

            if (bestRoad == null || bestDist > snapRadius)
            {
                return false;
            }

            var right = Vector3.Cross(Vector3.up, bestTangent); // right-hand traffic
            var lateral = Vector3.Dot(mousePos - bestProj, right);
            bool onRightSide = lateral >= 0f;

            var laneCenter = bestProj + (onRightSide ? right : -right) * SimulationConfig.VehicleLaneOffset;
            var forward = onRightSide ? bestTangent : -bestTangent;

            snappedPos = new Vector3(laneCenter.x, 0f, laneCenter.z);
            snappedRot = Quaternion.LookRotation(forward, Vector3.up);
            laneRight = right; // points horizontally to the road's right side (perpendicular to tangent)
            laneTangent = forward.normalized; // normalized forward vector along lane (vehicle's forward)
            roadId = bestRoad.id;
            return true;
        }


        private void SetPreviewColor(bool valid)
        {
            if (_previewEntity?.gameObject == null || _previewRenderers.Count == 0)
            {
                return;
            }
            Color c = valid ? new Color(0f, 1f, 0f, previewAlpha) : new Color(1f, 0f, 0f, previewAlpha);
            _mpb ??= new MaterialPropertyBlock();
            _mpb.SetColor("_Color", c);
            foreach (var r in _previewRenderers)
            {
                if (r == null)
                {
                    continue;
                }
                var shared = r.sharedMaterial;
                if (shared != null && shared.HasProperty("_Color"))
                {
                    r.SetPropertyBlock(_mpb);
                }
                else
                {
                    var instanced = r.material;
                    if (instanced != null)
                    {
                        instanced.color = c;
                    }
                }
            }
        }

        private void CachePreviewRenderers(GameObject go)
        {
            _previewRenderers.Clear();
            _previewRenderers.AddRange(go.GetComponentsInChildren<Renderer>());
        }

        private bool TryGetMouseGround(out Vector3 hitPos)
        {
            var cam = Camera.main;
            if (cam == null)
            {
                hitPos = Vector3.zero;
                return false;
            }

            var ray = cam.ScreenPointToRay(Input.mousePosition);
            var plane = new Plane(Vector3.up, 0f);
            if (plane.Raycast(ray, out var enter) && enter > 0f)
            {
                hitPos = ray.GetPoint(enter);
                return true;
            }

            hitPos = Vector3.zero;
            return false;
        }
    }
}
