using System.Collections.Generic;
using CitySimulation.Geometry;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.Placement_hangonbuttons
{
    /// <summary>
    /// Destroy tool: toggle with button; while active, left-click deletes hit entities via ObjectManager.DestroyObject.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public class DestroyPlacementUI : MonoBehaviour
    {
        [SerializeField] private string buttonName = "destory";
        [SerializeField] private float roadPickRadius = 1.2f; // 允许几何选中的最大半径（XZ 平面）

        private ObjectManager _objectManager;
        private bool _destroyMode;

        private void Awake()
        {
            _objectManager = GameServices.ObjectManager;
        }

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui.rootVisualElement;
            var button = root.Q<Button>(buttonName);
            if (button == null)
            {
                Debug.LogWarning($"[DestroyPlacementUI] Button '{buttonName}' not found.");
                return;
            }
            button.clicked += ToggleMode;
        }

        private void OnDisable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            var button = root?.Q<Button>(buttonName);
            if (button != null)
            {
                button.clicked -= ToggleMode;
            }
            _destroyMode = false;
        }

        private void Update()
        {
            // Allow Esc to exit destroy mode
            if (_destroyMode && Input.GetKeyDown(KeyCode.Escape))
            {
                _destroyMode = false;
                return;
            }

            if (!_destroyMode)
            {
                return;
            }

            if (Input.GetMouseButtonDown(0))
            {
                TryDestroyUnderMouse();
            }
        }

        private void ToggleMode()
        {
            _destroyMode = !_destroyMode;
        }

        private void TryDestroyUnderMouse()
        {
            var cam = Camera.main;
            if (cam == null)
            {
                return;
            }

            var ray = cam.ScreenPointToRay(Input.mousePosition);
            Vector3? hitPoint = null;

            // First: try collider hit
            if (Physics.Raycast(ray, out var hit, 1000f))
            {
                hitPoint = hit.point;
                var entity = _objectManager.FindByGameObject(hit.collider.gameObject);
                if (entity != null)
                {
                    _objectManager.DestroyObject(entity.id);
                    return;
                }
            }

            // Fallback: project to ground and pick nearest road by geometry (no collider needed)
            if (!hitPoint.HasValue)
            {
                if (ray.direction.y != 0f)
                {
                    float t = -ray.origin.y / ray.direction.y;
                    if (t > 0f)
                    {
                        hitPoint = ray.origin + ray.direction * t;
                    }
                }
            }

            if (!hitPoint.HasValue)
            {
                return;
            }

            if (TryPickNearestRoad(hitPoint.Value, roadPickRadius, out var road))
            {
                _objectManager.DestroyObject(road.id);
            }
        }

        private bool TryPickNearestRoad(Vector3 point, float maxRadius, out RoadEntity road)
        {
            road = null;
            float maxSqr = maxRadius * maxRadius;
            float best = float.MaxValue;

            foreach (var entity in _objectManager.GetAllEntities())
            {
                if (entity is not RoadEntity r || r.controlPoints == null || r.controlPoints.Count < 2)
                {
                    continue;
                }

                var distSqr = GeometryUtils.MinSqrDistanceToPolylineXZ(point, r.controlPoints);
                if (distSqr < best && distSqr <= maxSqr)
                {
                    best = distSqr;
                    road = r;
                }
            }

            return road != null;
        }
    }
}
