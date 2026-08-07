using CitySimulation.Global;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.RunTime.Running
{
    /// <summary>
    /// Binds UI Toolkit SliderInt (default: "set_StepRepeat") to SimulationConfig.RuntimeStepRepeat.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed class RuntimeStepRepeatSliderBinder : MonoBehaviour
    {
        [SerializeField] private string sliderName = "set_StepRepeat";

        private SliderInt _slider;

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _slider = root?.Q<SliderInt>(sliderName);

            if (_slider == null)
            {
                Debug.LogWarning($"[RuntimeStepRepeatSliderBinder] SliderInt '{sliderName}' not found.");
                return;
            }

            // UI -> config
            _slider.RegisterValueChangedCallback(OnSliderChanged);

            // config -> UI (initialize)
            if (SimulationConfig.RuntimeStepRepeat > 0)
            {
                _slider.SetValueWithoutNotify(SimulationConfig.RuntimeStepRepeat);
            }
            else
            {
                SimulationConfig.RuntimeStepRepeat = Mathf.Max(1, _slider.value);
            }
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
            SimulationConfig.RuntimeStepRepeat = Mathf.Max(1, evt.newValue);
        }
    }
}
