using CitySimulation.GameObjects;
using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.Map_manage
{
    [RequireComponent(typeof(UIDocument))]
    public class LoadMapUI : MonoBehaviour
    {
        [SerializeField] private string buttonName = "loadMap_button";
        [SerializeField] private string nameField = "loadMap_name";

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
                Debug.LogWarning($"[LoadMapUI] Button '{buttonName}' not found.");
                return;
            }
            if (_nameField == null)
            {
                Debug.LogWarning($"[LoadMapUI] Name field '{nameField}' not found. Loading default map.");
            }

            _button.clicked += OnLoadClicked;
        }

        private void OnDisable()
        {
            if (_button != null)
            {
                _button.clicked -= OnLoadClicked;
            }
            _button = null;
            _nameField = null;
        }

        private void OnLoadClicked()
        {
            var name = _nameField?.value;
            if (!string.IsNullOrEmpty(name))
            {
                _mapManager.SetCurrentMapId(name);
                _mapManager.LoadMap();
                Debug.Log($"[LoadMapUI] Loaded map '{name}'.");
            }
            else
            {
                Debug.Log("[LoadMapUI] Name empty: loading current map id.");
                _mapManager.LoadMap();
            }
        }
    }
}
