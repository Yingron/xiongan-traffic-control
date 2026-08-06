using System.Collections.Generic;
using CitySimulation.DTO;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;

namespace CitySimulation.Runtime.Test_BackendServer
{
    public sealed class Test_BackendServer
    {
        public List<VehicleDecisionAction> Decide(IReadOnlyList<VehicleObverse> requests)
        {
            var result = new List<VehicleDecisionAction>(requests?.Count ?? 0);
            if (requests == null)
            {
                return result;
            }

            for (int i = 0; i < requests.Count; i++)
            {
                var request = requests[i];
                if (request.GameStatus == GameDecisionStatus.NoDecisionNeeded
                    || request.GameStatus == GameDecisionStatus.GameCompleted)
                {
                    result.Add(VehicleDecisionAction.NoOperation);
                    continue;
                }

                result.Add(VehicleDecisionAction.Right);
            }

            return result;
        }

        public List<TrafficPhaseControlAction> DecideTraffic(IReadOnlyList<TrafficObverse> requests)
        {
            var result = new List<TrafficPhaseControlAction>(requests?.Count ?? 0);
            if (requests == null)
            {
                return result;
            }

            for (int i = 0; i < requests.Count; i++)
            {
                var request = requests[i];
                if (request.GameStatus == GameDecisionStatus.NoDecisionNeeded
                    || request.GameStatus == GameDecisionStatus.GameCompleted)
                {
                    result.Add(TrafficPhaseControlAction.NoOperation);
                    continue;
                }

                result.Add(TrafficPhaseControlAction.Extend3Seconds);
            }

            return result;
        }
    }
}
