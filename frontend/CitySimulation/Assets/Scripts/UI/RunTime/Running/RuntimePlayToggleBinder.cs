using CitySimulation.Global;
using CitySimulation.Runtime.Simulation;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.RunTime.Running
{
    /// <summary>
    /// Binds a UI Toolkit Toggle (default: "running_play") to adding/removing
    /// <see cref="SimulationRuntimeDriver"/> on a target GameObject
    /// (default object name: "SimulationRuntimeDriver").
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed class RuntimePlayToggleBinder : MonoBehaviour
    {
        [SerializeField] private string toggleName = "running_play";
        [SerializeField] private string lowSpeedToggleName = "low_speed_mode";
        [SerializeField] private string targetObjectName = "SimulationRuntimeDriver";
        [SerializeField] private bool createTargetIfMissing = true;

        private Toggle _toggle;
        private Toggle _lowSpeedToggle;

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _toggle = root?.Q<Toggle>(toggleName);

            if (_toggle == null)
            {
                Debug.LogWarning($"[RuntimePlayToggleBinder] Toggle '{toggleName}' not found.");
                return;
            }

            _toggle.RegisterValueChangedCallback(OnToggleChanged);
            SyncToggleFromScene();

            _lowSpeedToggle = root?.Q<Toggle>(lowSpeedToggleName) ?? root?.Q<Toggle>("togglelow_speed_mode");
            if (_lowSpeedToggle != null)
            {
                _lowSpeedToggle.RegisterValueChangedCallback(OnLowSpeedToggleChanged);
                _lowSpeedToggle.SetValueWithoutNotify(SimulationConfig.RuntimeLowSpeedMode);
            }
        }

        private void OnDisable()
        {
            if (_toggle != null)
            {
                _toggle.UnregisterValueChangedCallback(OnToggleChanged);
                _toggle = null;
            }

            if (_lowSpeedToggle != null)
            {
                _lowSpeedToggle.UnregisterValueChangedCallback(OnLowSpeedToggleChanged);
                _lowSpeedToggle = null;
            }
        }

        private void OnToggleChanged(ChangeEvent<bool> evt)
        {
            ApplyRunningState(evt.newValue);
        }

        private static void OnLowSpeedToggleChanged(ChangeEvent<bool> evt)
        {
            SimulationConfig.RuntimeLowSpeedMode = evt.newValue;
        }

        private void SyncToggleFromScene()
        {
            var target = ResolveTargetObject();
            bool hasDriver = target != null && target.GetComponent<SimulationRuntimeDriver>() != null;

            _toggle.SetValueWithoutNotify(hasDriver);
        }

        private void ApplyRunningState(bool running)
        {
            var target = ResolveTargetObject();
            if (target == null)
            {
                Debug.LogWarning($"[RuntimePlayToggleBinder] Target object '{targetObjectName}' not found.");
                if (_toggle != null)
                {
                    _toggle.SetValueWithoutNotify(false);
                }
                return;
            }

            var driver = target.GetComponent<SimulationRuntimeDriver>();

            if (running)
            {
                if (driver == null)
                {
                    target.AddComponent<SimulationRuntimeDriver>();
                }
                return;
            }

            if (driver != null)
            {
                if (Application.isPlaying)
                {
                    Destroy(driver);
                }
                else
                {
                    DestroyImmediate(driver);
                }
            }
        }

        private GameObject ResolveTargetObject()
        {
            var target = GameObject.Find(targetObjectName);
            if (target == null && createTargetIfMissing)
            {
                target = new GameObject(targetObjectName);
            }

            return target;
        }
    }
}
