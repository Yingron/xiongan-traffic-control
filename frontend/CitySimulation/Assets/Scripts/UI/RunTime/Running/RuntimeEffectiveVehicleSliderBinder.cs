using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.RunTime.Running
{
    /// <summary>
    /// Binds UI Toolkit SliderInt (default: "set_effective_vehicle")
    /// to SimulationConfig.RuntimeEffectiveVehicleCount.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed class RuntimeEffectiveVehicleSliderBinder : MonoBehaviour
    {
        [SerializeField] private string sliderName = "set_effective_vehicle";

        private SliderInt _slider;

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _slider = root?.Q<SliderInt>(sliderName);

            if (_slider == null)
            {
                Debug.LogWarning($"[RuntimeEffectiveVehicleSliderBinder] SliderInt '{sliderName}' not found.");
                return;
            }

            _slider.RegisterValueChangedCallback(OnSliderChanged);

            int clamped = Mathf.Clamp(
                Mathf.Max(1, SimulationConfig.RuntimeEffectiveVehicleCount),
                _slider.lowValue,
                _slider.highValue);

            SimulationConfig.RuntimeEffectiveVehicleCount = clamped;
            _slider.SetValueWithoutNotify(clamped);
        }

        private void OnDisable()
        {
            if (_slider != null)
            {
                _slider.UnregisterValueChangedCallback(OnSliderChanged);
                _slider = null;
            }
        }

        private static void OnSliderChanged(ChangeEvent<int> evt)
        {
            SimulationConfig.RuntimeEffectiveVehicleCount = Mathf.Max(1, evt.newValue);
        }
    }
}