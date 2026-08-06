using CitySimulation.Runtime.Simulation;
using UnityEngine;
using UnityEngine.UIElements;

namespace CitySimulation.UI.RunTime.Running
{
    /// <summary>
    /// Binds a UI Toolkit Toggle (default: "running_play_backend") to enabling/disabling
    /// <see cref="NetworkInterface"/> TCP server.
    /// </summary>
    [RequireComponent(typeof(UIDocument))]
    public sealed class RuntimeBackendToggleBinder : MonoBehaviour
    {
        [SerializeField] private string toggleName = "running_play_backend";

        private Toggle _toggle;

        private void OnEnable()
        {
            var ui = GetComponent<UIDocument>();
            var root = ui != null ? ui.rootVisualElement : null;
            _toggle = root?.Q<Toggle>(toggleName);

            if (_toggle == null)
            {
                Debug.LogWarning($"[RuntimeBackendToggleBinder] Toggle '{toggleName}' not found.");
                return;
            }

            _toggle.RegisterValueChangedCallback(OnToggleChanged);

            // In play mode, we want the backend server state to follow the Toggle's initial value
            // (e.g. set in UXML via value="true"), so that the backend can connect immediately
            // after pressing Play or running a built player.
            if (Application.isPlaying)
            {
                ApplyBackendState(_toggle.value);
                SyncToggleFromScene();
            }
            else
            {
                SyncToggleFromScene();
            }
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
            ApplyBackendState(evt.newValue);
        }

        private void SyncToggleFromScene()
        {
            var network = ResolveNetworkInterface();
            // In edit mode: reflect the scene's AutoStart flag.
            // In play mode: reflect actual running state.
            bool enabled = network != null && (Application.isPlaying ? network.IsServerRunning : network.AutoStart);
            _toggle.SetValueWithoutNotify(enabled);
        }

        private void ApplyBackendState(bool enabled)
        {
            var network = ResolveNetworkInterface();
            if (network == null)
            {
                Debug.LogWarning("[RuntimeBackendToggleBinder] NetworkInterface not found.");
                _toggle?.SetValueWithoutNotify(false);
                return;
            }

            network.SetServerEnabled(enabled);
        }

        private static NetworkInterface ResolveNetworkInterface()
        {
            return FindObjectOfType<NetworkInterface>(includeInactive: true);
        }
    }
}
