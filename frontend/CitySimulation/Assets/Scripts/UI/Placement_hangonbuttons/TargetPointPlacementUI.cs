using System;
using CitySimulation.DTO;
using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.Placement_hangonbuttons
{
    [RequireComponent(typeof(UIDocument))]
    public class TargetPointPlacementUI : MonoBehaviour
    {
        [SerializeField] private string buttonName = "createTargetPoint";
        [SerializeField] private string styleId = "red_sphere";

        private ObjectManager objectManager;
        private PrefabFactory factory;

        private TargetPointEntity previewEntity;
        private bool targetPointPlacementMode;

        private string activeTargetPointId;
        private bool vehicleAssignMode;

        private Button boundButton;

        private void Awake()
        {
            factory = GameServices.Prefabs;
            objectManager = GameServices.ObjectManager;
        }

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            boundButton = root?.Q<Button>(buttonName);
            if (boundButton == null)
            {
                Debug.LogWarning($"[TargetPointPlacementUI] Button '{buttonName}' not found.");
                return;
            }

            boundButton.clicked += OnCreateTargetPointClicked;
        }

        private void OnDisable()
        {
            if (boundButton != null)
            {
                boundButton.clicked -= OnCreateTargetPointClicked;
            }

            HidePreview();
            targetPointPlacementMode = false;
            vehicleAssignMode = false;
            activeTargetPointId = null;
        }

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.Escape) && (targetPointPlacementMode || vehicleAssignMode))
            {
                ExitAllModes();
                Debug.Log("[TargetPointPlacementUI] Exit target-point placement/assign mode (Esc).");
                return;
            }

            if (targetPointPlacementMode)
            {
                UpdatePreviewOnGroundPlane();

                if (Input.GetMouseButtonDown(0))
                {
                    TryPlaceTargetPointAndEnterAssignMode();
                }

                return;
            }

            if (vehicleAssignMode && Input.GetMouseButtonDown(0))
            {
                TryAssignTargetPointToClickedVehicle();
            }
        }

        private void OnCreateTargetPointClicked()
        {
            if (vehicleAssignMode)
            {
                vehicleAssignMode = false;
            }

            if (!targetPointPlacementMode)
            {
                targetPointPlacementMode = true;
                EnsurePreview();
                return;
            }

            TryPlaceTargetPointAndEnterAssignMode();
        }

        private void EnsurePreview()
        {
            if (previewEntity != null && previewEntity.gameObject != null)
            {
                previewEntity.gameObject.SetActive(true);
                return;
            }

            var dto = new TargetPointDTO
            {
                id = "__preview_target_point",
                category = MapCategory.TargetPoint,
                styleId = styleId,
                position = Vector3.zero,
                rotation = Quaternion.identity
            };

            previewEntity = factory.CreateEntity(dto) as TargetPointEntity;
            if (previewEntity?.gameObject != null)
            {
                previewEntity.gameObject.SetActive(true);
            }
        }

        private void HidePreview()
        {
            if (previewEntity?.gameObject != null)
            {
                previewEntity.gameObject.SetActive(false);
            }
        }

        private void UpdatePreviewOnGroundPlane()
        {
            if (previewEntity == null)
            {
                EnsurePreview();
            }

            if (previewEntity == null)
            {
                return;
            }

            if (!TryGetMouseGround(out var pos))
            {
                return;
            }

            previewEntity.ApplyTransform(pos, Quaternion.identity);
        }

        private void TryPlaceTargetPointAndEnterAssignMode()
        {
            if (!TryGetMouseGround(out var pos))
            {
                return;
            }

            var dto = new TargetPointDTO
            {
                id = Guid.NewGuid().ToString(),
                category = MapCategory.TargetPoint,
                styleId = styleId,
                position = pos,
                rotation = Quaternion.identity
            };

            var entity = objectManager.CreateObject(dto, need_validate: false) as TargetPointEntity;
            if (entity == null)
            {
                Debug.LogWarning("[TargetPointPlacementUI] Failed to place target point.");
                return;
            }

            activeTargetPointId = entity.id;
            targetPointPlacementMode = false;
            vehicleAssignMode = true;
            HidePreview();

            Debug.Log($"[TargetPointPlacementUI] Placed target point id={entity.id} at {entity.position}. Enter vehicle-assign mode.");
        }

        private void TryAssignTargetPointToClickedVehicle()
        {
            if (string.IsNullOrEmpty(activeTargetPointId))
            {
                return;
            }

            var cam = Camera.main;
            if (cam == null)
            {
                return;
            }

            var ray = cam.ScreenPointToRay(Input.mousePosition);
            var hits = Physics.RaycastAll(ray, 1000f);
            if (hits == null || hits.Length == 0)
            {
                return;
            }

            Array.Sort(hits, (a, b) => a.distance.CompareTo(b.distance));
            for (int i = 0; i < hits.Length; i++)
            {
                var hit = hits[i];
                if (hit.collider == null)
                {
                    continue;
                }

                var entity = objectManager.FindByGameObject(hit.collider.gameObject);
                if (entity is not VehicleEntity vehicle)
                {
                    continue;
                }

                vehicle.targetPointId = activeTargetPointId;
                Debug.Log($"[TargetPointPlacementUI] Assign targetPointId={activeTargetPointId} to vehicleId={vehicle.id}.");
                return;
            }

            Debug.Log("[TargetPointPlacementUI] Clicked position has no vehicle to assign.");
        }

        private void ExitAllModes()
        {
            targetPointPlacementMode = false;
            vehicleAssignMode = false;
            activeTargetPointId = null;
            HidePreview();
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
                hitPos.y = 0f;
                return true;
            }

            hitPos = Vector3.zero;
            return false;
        }
    }
}
