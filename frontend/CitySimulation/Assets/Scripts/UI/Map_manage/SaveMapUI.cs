using CitySimulation.GameObjects;
using CitySimulation.GameObjects.Entities;
using CitySimulation.DTO;
using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.Placement_hangonbuttons
{
    /// <summary>
    /// Binds a UI Toolkit button to save the current map using MapManager/ObjectManager state.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public class SaveMapUI : MonoBehaviour
    {
        [SerializeField] private string buttonName = "saveMap_button";
        [SerializeField] private string nameField = "saveMap_name";

        private MapManager _mapManager;
        private Button _button;
        private TextField _nameField;

        private void Awake()
        {
            _mapManager = GameServices.MapManager ?? new MapManager(GameServices.ObjectManager);
        }

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _button = root?.Q<Button>(buttonName);
            _nameField = root?.Q<TextField>(nameField);

            if (_button == null)
            {
                Debug.LogWarning($"[SaveMapUI] Button '{buttonName}' not found.");
                return;
            }
            if (_nameField == null)
            {
                Debug.LogWarning($"[SaveMapUI] Name field '{nameField}' not found. Using current map id.");
            }

            _button.clicked += OnSaveClicked;
        }

        private void OnDisable()
        {
            if (_button != null)
            {
                _button.clicked -= OnSaveClicked;
            }
            _button = null;
            _nameField = null;
        }

        private void OnSaveClicked()
        {
            var objectManager = GameServices.ObjectManager;
            if (objectManager != null)
            {
                int emergencyCount = 0;
                int missingTargetCount = 0;

                foreach (var entity in objectManager.GetAllEntities())
                {
                    if (entity is not VehicleEntity vehicle)
                    {
                        continue;
                    }

                    if (vehicle.vehicleType != VehicleType.Emergency)
                    {
                        continue;
                    }

                    emergencyCount++;
                    if (string.IsNullOrEmpty(vehicle.targetPointId))
                    {
                        missingTargetCount++;
                    }
                }

                if (missingTargetCount == 0)
                {
                    Debug.Log("[SaveMapUI] 所有应急车辆都有目标");
                }
                else
                {
                    Debug.Log("[SaveMapUI] 有应急车辆没有目标");
                }
            }
            else
            {
                Debug.LogWarning("[SaveMapUI] ObjectManager is null; skip emergency vehicle target validation.");
            }

            var name = _nameField?.value;
            if (!string.IsNullOrEmpty(name))
            {
                _mapManager.SetCurrentMapId(name);
            }

            if (objectManager != null)
            {
                GameServices.RegisterRuntimeServices();
                GameServices.TrafficService?.RebuildFromRoadIntersectionsForMapSave(objectManager);
            }

            bool ok = _mapManager.SaveMap();
            Debug.Log(ok ? "[SaveMapUI] Map saved." : "[SaveMapUI] Map save failed.");
        }
    }
}
