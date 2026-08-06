using System;
using System.Collections.Generic;
using CitySimulation.Global;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;
using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    public sealed class BackendClinet
    {
        readonly global::CitySimulation.Runtime.Test_BackendServer.Test_BackendServer server = new();

        float sendTimer;
        float elapsedTimeSeconds;
        // tem
        // bool loggedFirstVehicleObverse;

        public void Tick(float dt)
        {
            if (dt <= 0f)
            {
                return;
            }

            elapsedTimeSeconds += dt;
            sendTimer += dt;
            if (sendTimer < global::CitySimulation.Global.SimulationConfig.BackendDecisionSendIntervalSeconds)
            {
                return;
            }

            sendTimer = 0f;
            
            BackendDecide();

            var vehicleService = GameServices.VehicleService;
            if (vehicleService != null)
            {
                List<float> currentStepReward = GameServices.VehicleService.GetCurrentStepTotalReward(elapsedTimeSeconds);
                
                int n = Mathf.Max(1, SimulationConfig.RuntimeEffectiveVehicleCount);
                int countToSum = Mathf.Min(n, currentStepReward.Count);

                float sum = 0f;
                for (int i = 0; i < countToSum; i++)
                {
                    sum += currentStepReward[i];
                }

                float reward = sum / n;
                Debug.Log($"当前步数的奖励(前{n}辆平均): {reward}");
            }
        }

        public void Release()
        {
            sendTimer = 0f;
            elapsedTimeSeconds = 0f;

            // tmp
            // loggedFirstVehicleObverse = false;
        }

        void BackendDecide()
        {
            var vehicleService = GameServices.VehicleService;
            var trafficService = GameServices.TrafficService;
            if (vehicleService == null && trafficService == null)
            {
                return;
            }

            // request vehicles
            if (vehicleService != null)
            {
                var VehicleObverseList = vehicleService.GetEmergencyVehicleObverse();

                // //tmp

                // if (!loggedFirstVehicleObverse && VehicleObverseList.Count > 0)
                // {
                //     var first = VehicleObverseList[0];
                //     Debug.Log($"[BackendClinet] First VehicleObverse: pos=({first.PositionX:F3}, {first.PositionZ:F3}), sin={first.SinThetaToTarget:F3}, cos={first.CosThetaToTarget:F3}, dist={first.DistanceToTarget:F3}, status={first.GameStatus}");
                //     loggedFirstVehicleObverse = true;
                // }

                var actions = server.Decide(VehicleObverseList);
                vehicleService.ApplyVehicleDecision(actions);
            }

            // request traffic
            if (trafficService != null)
            {
                var trafficObverseList = trafficService.BuildTrafficLightObverse();

                // // ======= log =======
                // Debug.Log($"[BackendClinet] trafficObverseList count={trafficObverseList.Count}");
                // for (int i = 0; i < trafficObverseList.Count; i++)
                // {
                //     var t = trafficObverseList[i];
                //     Debug.Log(
                //         $"[BackendClinet] trafficObverse[{i}] green=({t.GreenDir0},{t.GreenDir1}) " +
                //         $"emergency=({t.EmergencyCountDir0},{t.EmergencyCountDir1}) " +
                //         $"congestion={t.CongestionCountInRange} " +
                //         $"extendLeft={t.AvailableExtendLeft} timeLeft={t.LightTimeLeft:F2} status={t.GameStatus}");
                // }
                // // ======= end =======
                var trafficActions = server.DecideTraffic(trafficObverseList);
                trafficService.ApplyTrafficDecision(trafficActions);
            }
        }


    }
}