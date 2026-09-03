using UnityEngine;

namespace CitySimulation.Runtime.Visualization
{
    /// <summary>
    /// 可视化系统启动器 — 一键创建完整的 SUMO 可视化系统。
    ///
    /// 用法:
    ///   1. 在场景中创建空 GameObject，挂载此脚本
    ///   2. 确保场景中已有路网和信号灯（XionganRoadBootstrap 已构建）
    ///   3. 运行场景，系统自动连接 Python 可视化服务器
    ///
    /// 或者通过菜单: 雄安路网 / 创建可视化系统
    /// </summary>
    [DisallowMultipleComponent]
    public class VisualizationBootstrap : MonoBehaviour
    {
        [Header("服务器配置")]
        [Tooltip("Python 可视化服务器地址")]
        public string serverHost = "127.0.0.1";
        [Tooltip("WebSocket 端口")]
        public int serverPort = 8765;

        [Header("运行选项")]
        [Tooltip("启动时自动连接服务器")]
        public bool autoConnect = true;
        [Tooltip("是否禁用本地车辆仿真（由 SUMO 数据驱动）")]
        public bool disableLocalSimulation = true;

        SumoWebSocketClient _wsClient;
        SumoVisualizationBridge _bridge;
        TrafficVisualizationUI _ui;

        void Awake()
        {
            // 添加必要的组件（如果不存在）
            _wsClient = GetComponent<SumoWebSocketClient>();
            if (_wsClient == null)
            {
                _wsClient = gameObject.AddComponent<SumoWebSocketClient>();
            }

            _bridge = GetComponent<SumoVisualizationBridge>();
            if (_bridge == null)
            {
                _bridge = gameObject.AddComponent<SumoVisualizationBridge>();
            }

            _ui = GetComponent<TrafficVisualizationUI>();
            if (_ui == null)
            {
                _ui = gameObject.AddComponent<TrafficVisualizationUI>();
            }

            // AI 云脑诊断面板（赛道 C）：自动挂载，运行时构建 UI，无需手动搭建
            if (GetComponent<LlmAlertPanel>() == null)
            {
                gameObject.AddComponent<LlmAlertPanel>();
            }

            // 配置 WebSocket 客户端
            _wsClient.serverHost = serverHost;
            _wsClient.serverPort = serverPort;
            _wsClient.autoConnect = autoConnect;

            // 配置可视化桥接器
            _bridge.wsClient = _wsClient;

            // 如果禁用本地仿真，关闭 SimulationRuntimeDriver 的车辆生成
            if (disableLocalSimulation)
            {
                var driver = FindObjectOfType<Simulation.SimulationRuntimeDriver>();
                if (driver != null)
                {
                    driver.spawnVehiclesOnStart = false;
                    Debug.Log("[VisualizationBootstrap] 已禁用本地车辆仿真，使用 SUMO 数据驱动");
                }
            }
        }
    }
}
