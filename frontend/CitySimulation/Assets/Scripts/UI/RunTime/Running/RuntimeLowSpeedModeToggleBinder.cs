using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.RunTime.Running
{
    /// <summary>
    /// Binds UI Toolkit Toggle (default: "low_speed_mode") to SimulationConfig.RuntimeLowSpeedMode.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed class RuntimeLowSpeedModeToggleBinder : MonoBehaviour
    {
        [SerializeField] private string toggleName = "low_speed_mode";

        private Toggle _toggle;

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _toggle = root?.Q<Toggle>(toggleName) ?? root?.Q<Toggle>("togglelow_speed_mode");

            if (_toggle == null)
            {
                Debug.LogWarning($"[RuntimeLowSpeedModeToggleBinder] Toggle '{toggleName}' not found.");
                return;
            }

            _toggle.RegisterValueChangedCallback(OnToggleChanged);
            _toggle.SetValueWithoutNotify(SimulationConfig.RuntimeLowSpeedMode);
        }

        private void OnDisable()
        {
            if (_toggle != null)
            {
                _toggle.UnregisterValueChangedCallback(OnToggleChanged);
                _toggle = null;
            }
        }

        private static void OnToggleChanged(ChangeEvent<bool> evt)
        {
            SimulationConfig.RuntimeLowSpeedMode = evt.newValue;
        }
    }
}
