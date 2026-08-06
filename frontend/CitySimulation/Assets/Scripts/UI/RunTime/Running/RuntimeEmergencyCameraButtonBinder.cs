using System.Collections.Generic;
using CitySimulation.CameraControls;
using CitySimulation.DTO;
using CitySimulation.GameObjects.Entities;
using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.RunTime.Running
{
    [RequireComponent(typeof(UIDocument))]
    public sealed class RuntimeEmergencyCameraButtonBinder : MonoBehaviour
    {
        [SerializeField] private string buttonName = "follow_emergency_vehicle";
        [SerializeField] private string followText = "follow emergency";
        [SerializeField] private string releaseText = "free camera";

        private Button _button;
        private EmergencyVehicleCameraFollow _cameraFollow;

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _button = root?.Q<Button>(buttonName);

            if (_button == null)
            {
                Debug.LogWarning($"[RuntimeEmergencyCameraButtonBinder] Button '{buttonName}' not found.");
                return;
            }

            _button.clicked += OnButtonClicked;
            SyncButtonText();
        }

        private void OnDisable()
        {
            if (_button != null)
            {
                _button.clicked -= OnButtonClicked;
                _button = null;
            }
        }

        private void OnButtonClicked()
        {
            var cameraFollow = ResolveCameraFollow();
            if (cameraFollow == null)
            {
                Debug.LogWarning("[RuntimeEmergencyCameraButtonBinder] Main Camera not found.");
                return;
            }

            if (cameraFollow.IsFollowing)
            {
                cameraFollow.StopFollowing();
                SyncButtonText();
                return;
            }

            var target = PickEmergencyVehicle();
            if (target == null)
            {
                Debug.LogWarning("[RuntimeEmergencyCameraButtonBinder] No active emergency vehicle is available to follow.");
                SyncButtonText();
                return;
            }

            cameraFollow.Follow(target);
            SyncButtonText();
        }

        private void SyncButtonText()
        {
            if (_button == null)
            {
                return;
            }

            var cameraFollow = ResolveCameraFollow();
            _button.text = cameraFollow != null && cameraFollow.IsFollowing ? releaseText : followText;
        }

        private EmergencyVehicleCameraFollow ResolveCameraFollow()
        {
            if (_cameraFollow != null)
            {
                return _cameraFollow;
            }

            var mainCamera = Camera.main;
            if (mainCamera == null)
            {
                return null;
            }

            _cameraFollow = mainCamera.GetComponent<EmergencyVehicleCameraFollow>();
            if (_cameraFollow == null)
            {
                _cameraFollow = mainCamera.gameObject.AddComponent<EmergencyVehicleCameraFollow>();
            }

            return _cameraFollow;
        }

        private static Transform PickEmergencyVehicle()
        {
            var candidates = new List<Transform>();

            var vehicleService = GameServices.VehicleService;
            if (vehicleService != null)
            {
                AddCandidateTransforms(vehicleService.GetEmergencyVehicles(), candidates);
            }
            else
            {
                var emergencyVehicles = new List<VehicleEntity>();
                foreach (var entity in GameServices.ObjectManager.GetAllEntities())
                {
                    if (entity is VehicleEntity vehicle && vehicle.vehicleType == VehicleType.Emergency)
                    {
                        emergencyVehicles.Add(vehicle);
                    }
                }

                AddCandidateTransforms(emergencyVehicles, candidates);
            }

            if (candidates.Count == 0)
            {
                return null;
            }

            return candidates[Random.Range(0, candidates.Count)];
        }

        private static void AddCandidateTransforms(IEnumerable<VehicleEntity> vehicles, List<Transform> candidates)
        {
            foreach (var vehicle in vehicles)
            {
                if (vehicle == null
                    || vehicle.gameObject == null
                    || !vehicle.gameObject.activeInHierarchy
                    || vehicle.gameStatus == GameDecisionStatus.GameCompleted)
                {
                    continue;
                }

                candidates.Add(vehicle.gameObject.transform);
            }
        }
    }
}
