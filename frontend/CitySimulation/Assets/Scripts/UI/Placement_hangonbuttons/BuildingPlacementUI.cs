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
    /// UI Toolkit binding: click the button (create_building_big_01) to enable placement mode.
    /// Shows a preview under mouse; green if valid, red if invalid; left-click to place.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public class BuildingPlacementUI : MonoBehaviour
    {
        [SerializeField] private float previewAlpha = 0.6f;

        [Serializable]
        private struct ButtonStyleMapping
        {
            public string buttonName;
            public string styleId;
        }

        [SerializeField] private ButtonStyleMapping[] mappings =
        {
            new ButtonStyleMapping { buttonName = "createBuilding_Sky_big_color01", styleId = "Sky_big_color01" },
            new ButtonStyleMapping { buttonName = "createBuilding_Fast_Food_color01", styleId = "Fast_Food_color01" }
        };
        private string styleId;
        private ObjectManager _objectManager;
        private PrefabFactory _factory;
        private MapEntity _previewEntity;
        private bool _placementMode;
        private readonly System.Collections.Generic.List<Renderer> _previewRenderers = new();
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
                Debug.LogWarning("[BuildingPlacementUI] No button/style mappings configured.");
                return;
            }

            // use first mapping as default style
            styleId = mappings[0].styleId;

            foreach (var mapping in mappings)
            {
                RegisterButton(root, mapping.buttonName, mapping.styleId);
            }
        }

        private void OnDisable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            // Unregister all handlers we added
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

        private void RegisterButton(VisualElement root, string targetButtonName, string targetStyleId)
        {
            if (string.IsNullOrEmpty(targetButtonName))
            {
                return;
            }

            var button = root?.Q<Button>(targetButtonName);
            if (button == null)
            {
                Debug.LogWarning($"[BuildingPlacementUI] Button '{targetButtonName}' not found.");
                return;
            }

            void Handler()
            {
                BeginPlacementForStyle(targetStyleId);
            }

            button.clicked += Handler;
            _registeredHandlers.Add((button, Handler));
        }

        private void BeginPlacementForStyle(string targetStyleId)
        {
            styleId = targetStyleId;
            // reset preview so next EnsurePreview uses the new style
            _previewEntity = null;
            HidePreview();
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

            if (!TryGetMouseWorld(out var hitPos))
            {
                return;
            }

            // project to ground (y=0)
            hitPos = ProjectToGround(hitPos);

            // move preview
            _previewEntity.ApplyTransform(hitPos, Quaternion.identity);

            // check validity against existing entities using collider-based validate
            bool valid = IsPositionValid(hitPos);
            SetPreviewColor(valid);

            if (valid && Input.GetMouseButtonDown(0))
            {
                PlaceBuilding(hitPos);
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

            var dto = new BuildingDTO
            {
                id = "__preview_building",
                category = MapCategory.Building,
                styleId = styleId,
                position = Vector3.zero,
                rotation = Quaternion.identity
            };
            _previewEntity = _factory.CreateEntity(dto);
            if (_previewEntity?.gameObject != null)
            {
                CachePreviewRenderers(_previewEntity.gameObject);
                SetPreviewColor(true); // default green-ish
            }
        }

        private void HidePreview()
        {
            if (_previewEntity?.gameObject != null)
            {
                _previewEntity.gameObject.SetActive(false);
            }
        }

        private bool IsPositionValid(Vector3 pos)
        {
            if (_previewEntity == null || _previewEntity.gameObject == null)
            {
                return false;
            }

            _previewEntity.ApplyTransform(pos, Quaternion.identity);
            var validation = _previewEntity.Validate(_objectManager);
            return validation.IsValid;
        }

        private void PlaceBuilding(Vector3 pos)
        {
            var dto = new BuildingDTO
            {
                id = Guid.NewGuid().ToString(),
                category = MapCategory.Building,
                styleId = styleId,
                position = pos,
                rotation = Quaternion.identity
            };
            var entity = _objectManager.CreateObject(dto);
            if (entity != null)
            {
                Debug.Log($"[BuildingPlacementUI] Placed building {entity.id} at {pos}.");
            }
        }

        private void SetPreviewColor(bool valid)
        {
            if (_previewEntity?.gameObject == null || _previewRenderers.Count == 0)
            {
                return;
            }
            Color c = valid ? new Color(0f, 1f, 0f, previewAlpha) : new Color(1f, 0f, 0f, previewAlpha);
            if (_mpb == null)
            {
                _mpb = new MaterialPropertyBlock();
            }
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

        private bool TryGetMouseWorld(out Vector3 hitPos)
        {
            var cam = Camera.main;
            if (cam == null)
            {
                hitPos = Vector3.zero;
                return false;
            }

            Ray ray = cam.ScreenPointToRay(Input.mousePosition);

            // Always compute intersection with the horizontal plane y=0.
            var plane = new Plane(Vector3.up, 0f);
            if (plane.Raycast(ray, out var enter) && enter > 0f)
            {
                hitPos = ProjectToGround(ray.GetPoint(enter));
                return true;
            }

    
            hitPos = Vector3.zero;
            return false;
        }

        private Vector3 ProjectToGround(Vector3 pos)
        {
            pos.y = 0f;
            return pos;
        }
    }
}
