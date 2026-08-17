using UnityEngine;

namespace CitySimulation.Runtime.Dqn
{
    /// <summary>
    /// Installs the real API dashboard in the City scene without requiring a
    /// hand-edited scene asset.  It is guarded by the 30-junction bootstrap name
    /// so ordinary prototype scenes do not create a backend session.
    /// </summary>
    public class DqnApiBootstrap : MonoBehaviour
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void InstallForThirtyJunctionScene()
        {
            if (!Application.isPlaying || FindObjectOfType<DqnControlClient>() != null) return;
            if (GameObject.Find("XionganRoadBootstrap") == null) return;
            new GameObject("DqnApiControl").AddComponent<DqnApiBootstrap>();
        }

        void Awake()
        {
            var client = gameObject.AddComponent<DqnControlClient>();
            client.apiBaseUrl = "http://127.0.0.1:8000/api/v1";
            client.scenario = "real_offpeak";
            client.modelId = "shared-dqn-real-offpeak-perf-1m-v1";
            gameObject.AddComponent<DqnDashboardUI>();
            gameObject.AddComponent<DqnTrafficLightApplier>();
            Debug.Log("[DqnControl] 已为 30 路口 City 场景安装真实数据 Dashboard 与 DQN 闭环。");
        }
    }
}
