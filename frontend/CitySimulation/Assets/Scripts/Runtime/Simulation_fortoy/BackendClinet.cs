using System;
using System.Collections.Generic;
using CitySimulation.DTO;
using CitySimulation.Global;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;
using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    public sealed class BackendClinet : IDisposable
    {
        // 为避免名称歧义，使用完全限定名称（与旧代码一致）
        private global::CitySimulation.Runtime.Test_BackendServer.Test_BackendServer _mockServer;
        private global::CitySimulation.Runtime.Test_BackendServer.Test_BackendServer MockServer
            => _mockServer ??= new global::CitySimulation.Runtime.Test_BackendServer.Test_BackendServer();

        // ============ 后端模式 ============
        public enum BackendMode
        {
            TestMock,      // 使用 Test_BackendServer（本地模拟，默认）
            BridgeTcp,     // 使用真实 TCP BridgeClient（连接 C bridge_server）
        }

        // ============ 状态 ============
        public BackendMode Mode { get; private set; } = BackendMode.TestMock;
        public BridgeClient Bridge { get; private set; }

        float sendTimer;
        float elapsedTimeSeconds;

        // ============ 统计 ============
        public int TotalRequests { get; private set; }
        public int FallbackCount { get; private set; }
        public float LastLatencyMs => Bridge?.LastLatencyMs ?? 0f;
        public bool IsBridgeConnected => Bridge?.IsConnected ?? false;

        // ============ 事件 ============
        public event Action<BackendMode> OnModeChanged;

        // ============ 初始化 ============
        public void Initialize(BackendMode mode = BackendMode.TestMock, string host = "127.0.0.1", int port = 5000)
        {
            Mode = mode;
            OnModeChanged?.Invoke(mode);

            if (mode == BackendMode.BridgeTcp)
            {
                Bridge = new BridgeClient { Host = host, Port = port };
                Bridge.Start();
                Debug.Log($"[BackendClinet] BridgeClient started → {host}:{port}");
            }
            else
            {
                Debug.Log("[BackendClinet] Using TestMock backend");
            }
        }

        public void Tick(float dt)
        {
            if (dt <= 0f) return;

            elapsedTimeSeconds += dt;
            sendTimer += dt;
            if (sendTimer < SimulationConfig.BackendDecisionSendIntervalSeconds)
            {
                return;
            }

            sendTimer = 0f;
            BackendDecide();

            // 奖励统计
            var vehicleService = GameServices.VehicleService;
            if (vehicleService != null)
            {
                List<float> currentStepReward = vehicleService.GetCurrentStepTotalReward(elapsedTimeSeconds);

                int n = Mathf.Max(1, SimulationConfig.RuntimeEffectiveVehicleCount);
                int countToSum = Mathf.Min(n, currentStepReward.Count);

                float sum = 0f;
                for (int i = 0; i < countToSum; i++)
                    sum += currentStepReward[i];

                float reward = sum / n;
                // 仅在 Bridge 模式下打印（减少噪音）
                if (Mode == BackendMode.BridgeTcp && TotalRequests % 50 == 0)
                {
                    Debug.Log($"[BackendClinet] step reward(avg): {reward:F3} | bridge={(Bridge != null && Bridge.IsConnected ? "OK" : "DOWN")} | latency={LastLatencyMs:F1}ms");
                }
            }
        }

        public void Release()
        {
            sendTimer = 0f;
            elapsedTimeSeconds = 0f;
        }

        public void Dispose()
        {
            Bridge?.Stop();
            Bridge?.Dispose();
        }

        // ============ 核心决策 ============
        void BackendDecide()
        {
            var vehicleService = GameServices.VehicleService;
            var trafficService = GameServices.TrafficService;
            if (vehicleService == null && trafficService == null) return;

            // 收集观测
            var vehicleObs = vehicleService?.GetEmergencyVehicleObverse() ?? new List<VehicleObverse>();
            var trafficObs = trafficService?.BuildTrafficLightObverse() ?? new List<TrafficObverse>();

            // 空观测跳过
            if (vehicleObs.Count == 0 && trafficObs.Count == 0) return;

            TotalRequests++;

            if (Mode == BackendMode.BridgeTcp && Bridge != null && Bridge.IsConnected)
            {
                // === 真实 TCP 请求 ===
                var response = Bridge.SendDecisionRequest(vehicleObs, trafficObs);

                if (response.status == "fallback")
                {
                    FallbackCount++;
                    ApplyFallback(vehicleObs, trafficObs, vehicleService, trafficService);
                }
                else
                {
                    ApplyResponse(response, vehicleService, trafficService);
                }
            }
            else
            {
                // === Test Mock（默认回退） ===
                // Vehicle decisions
                if (vehicleService != null && vehicleObs.Count > 0)
                {
                    var vehicleActions = MockServer.Decide(vehicleObs);
                    vehicleService.ApplyVehicleDecision(vehicleActions);
                }

                // Traffic decisions
                if (trafficService != null && trafficObs.Count > 0)
                {
                    var trafficActions = MockServer.DecideTraffic(trafficObs);
                    trafficService.ApplyTrafficDecision(trafficActions);
                }
            }
        }

        // ============ 响应应用 ============
        private void ApplyResponse(BridgeResponse response, VehicleService vehicleService, TrafficService trafficService)
        {
            // Vehicle actions (int[] → 通过 ApplyVehicleDecision(IReadOnlyList<int>))
            if (vehicleService != null && response.vehicleActions != null && response.vehicleActions.Count > 0)
            {
                vehicleService.ApplyVehicleDecision(response.vehicleActions);
            }

            // Traffic actions (int[] → 通过 ApplyTrafficDecision(IReadOnlyList<int>))
            if (trafficService != null && response.trafficActions != null && response.trafficActions.Count > 0)
            {
                trafficService.ApplyTrafficDecision(response.trafficActions);
            }
        }

        private void ApplyFallback(
            List<VehicleObverse> vehicleObs,
            List<TrafficObverse> trafficObs,
            VehicleService vehicleService,
            TrafficService trafficService)
        {
            FallbackCount++;

            if (vehicleService != null && vehicleObs.Count > 0)
            {
                var actions = MockServer.Decide(vehicleObs);
                vehicleService.ApplyVehicleDecision(actions);
            }

            if (trafficService != null && trafficObs.Count > 0)
            {
                var actions = MockServer.DecideTraffic(trafficObs);
                trafficService.ApplyTrafficDecision(actions);
            }
        }
    }
}
