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
    /// Road placement tool: left-click keeps adding vertices to a polyline preview; right-click finishes and creates the road; Esc cancels and exits.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public class RoadPlacementUI : MonoBehaviour
    {
        [SerializeField] private string buttonName = "createRoad";
        [SerializeField] private string styleId = "section";
        private ObjectManager _objectManager;
        private PrefabFactory _factory;
        private bool _placementMode;
        private readonly List<Vector3> _points = new();
        private LineRenderer _previewRenderer;
        private GameObject _previewObject;

        private void Awake()
        {
            _factory = GameServices.Prefabs;
            _objectManager = GameServices.ObjectManager;
        }

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui.rootVisualElement;
            var button = root.Q<Button>(buttonName);
            if (button == null)
            {
                Debug.LogWarning($"[RoadPlacementUI] Button '{buttonName}' not found.");
                return;
            }
            button.clicked += TogglePlacementMode;
        }

        private void OnDisable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            var button = root?.Q<Button>(buttonName);
            if (button != null)
            {
                button.clicked -= TogglePlacementMode;
            }
            ResetPreview();
        }

        private void Update()
        {
            // Allow Esc to exit placement mode for UX
            if (Input.GetKeyDown(KeyCode.Escape) && _placementMode)
            {
                CancelAndExit();
                return;
            }

            if (!_placementMode)
            {
                return;
            }

            // Left-click keeps adding vertices
            if (Input.GetMouseButtonDown(0))
            {
                if (TryGetMouseWorld(out var pos))
                {
                    AddPoint(pos);
                }
            }

            // Right-click finishes current road
            if (Input.GetMouseButtonDown(1))
            {
                FinishRoad();
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
                ResetPreview();
            }
        }

        private void AddPoint(Vector3 worldPos)
        {
            var p = SnapToGround(worldPos);
            _points.Add(p);
            UpdatePreview();
        }

        private void FinishRoad()
        {
            if (_points.Count < 2)
            {
                return;
            }

            // Create a new road entity per completed polyline
            var dto = new RoadDTO
            {
                id = System.Guid.NewGuid().ToString(),
                category = MapCategory.Road,
                styleId = styleId,
                position = _points[0],
                rotation = Quaternion.identity,
                controlPoints = new List<Vector3>(_points)
            };

            var entity = _objectManager.CreateObject(dto) as RoadEntity;
            if (entity == null)
            {
                Debug.LogWarning("[RoadPlacementUI] Road creation failed (validation).");
            }

            _points.Clear();
            UpdatePreview();
        }

        private bool TryGetMouseWorld(out Vector3 hitPos)
        {
            var cam = Camera.main;
            if (cam == null)
            {
                hitPos = Vector3.zero;
                return false;
            }

            Ray ray = cam.ScreenPointToRay(Input.mousePosition);
            if (Physics.Raycast(ray, out var hit, 500f))
            {
                hitPos = SnapToGround(hit.point);
                return true;
            }

            // fallback: intersect with plane y=0
            if (ray.direction.y != 0)
            {
                float t = -ray.origin.y / ray.direction.y;
                if (t > 0)
                {
                    hitPos = SnapToGround(ray.origin + ray.direction * t);
                    return true;
                }
            }

            hitPos = Vector3.zero;
            return false;
        }

        private Vector3 SnapToGround(Vector3 pos)
        {
            pos.y = 0f;
            return pos;
        }

        private void EnsurePreview()
        {
            if (_previewRenderer != null)
            {
                return;
            }

            _previewObject = new GameObject("RoadPreview");
            _previewRenderer = _previewObject.AddComponent<LineRenderer>();
            _previewRenderer.useWorldSpace = true;
            _previewRenderer.loop = false;
            _previewRenderer.widthMultiplier = 0.2f;
            _previewRenderer.material = new Material(Shader.Find("Sprites/Default"));
            _previewRenderer.startColor = Color.green;
            _previewRenderer.endColor = Color.green;
        }

        private void UpdatePreview()
        {
            EnsurePreview();
            _previewRenderer.positionCount = _points.Count;
            for (int i = 0; i < _points.Count; i++)
            {
                _previewRenderer.SetPosition(i, _points[i]);
            }
        }

        private void ResetPreview()
        {
            _points.Clear();
            if (_previewRenderer != null)
            {
                _previewRenderer.positionCount = 0;
            }
            if (_previewObject != null)
            {
                Destroy(_previewObject);
                _previewObject = null;
                _previewRenderer = null;
            }
        }

        private void CancelAndExit()
        {
            ResetPreview();
            _placementMode = false;
        }
    }
}
