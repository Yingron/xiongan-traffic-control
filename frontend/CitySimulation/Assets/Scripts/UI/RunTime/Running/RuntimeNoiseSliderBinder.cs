using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.RunTime.Running
{
    /// <summary>
    /// Binds UI Toolkit Toggle (default: "set_noise")
    /// to SimulationConfig.RuntimeObservationDelayEnabled.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed class RuntimeNoiseSliderBinder : MonoBehaviour
    {
        [SerializeField] private string toggleName = "set_noise";

        private Toggle _toggle;
        private bool _suppressCallback;

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _toggle = root?.Q<Toggle>(toggleName);

            if (_toggle == null)
            {
                Debug.LogWarning($"[RuntimeNoiseSliderBinder] Toggle '{toggleName}' not found.");
                return;
            }

            _toggle.RegisterValueChangedCallback(OnToggleChanged);
            _toggle.SetValueWithoutNotify(SimulationConfig.RuntimeObservationDelayEffective);
        }

        private void OnDisable()
        {
            if (_toggle != null)
            {
                _toggle.UnregisterValueChangedCallback(OnToggleChanged);
                _toggle = null;
            }
        }

        private void OnToggleChanged(ChangeEvent<bool> evt)
        {
            if (_suppressCallback)
            {
                return;
            }

            if (SimulationConfig.RuntimeObservationDelayOverrideActive)
            {
                _toggle?.SetValueWithoutNotify(SimulationConfig.RuntimeObservationDelayOverrideValue);
                return;
            }

            SimulationConfig.RuntimeObservationDelayEnabled = evt.newValue;
        }

        public void ApplyBackendOverride(bool enabled)
        {
            SimulationConfig.RuntimeObservationDelayOverrideActive = true;
            SimulationConfig.RuntimeObservationDelayOverrideValue = enabled;
            SimulationConfig.RuntimeObservationDelayEnabled = enabled;

            if (_toggle == null)
            {
                return;
            }

            _suppressCallback = true;
            _toggle.SetValueWithoutNotify(enabled);
            _suppressCallback = false;
        }
    }
}
