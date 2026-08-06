using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    public static class VehicleExpertActionHeuristic
    {
        const int NoOperation = 0;
        const int Straight = 1;
        const int Left = 2;
        const int Right = 3;
        const int UTurn = 4;

        const float FrontCosThreshold = 0.35f;
        const float BackCosThreshold = -0.35f;
        const float SideSinThreshold = 0.15f;

        public static int InferAction(float sinThetaToTarget, float cosThetaToTarget, bool needDecision)
        {
            if (!needDecision)
            {
                return NoOperation;
            }

            float sin = Mathf.Clamp(sinThetaToTarget, -1f, 1f);
            float cos = Mathf.Clamp(cosThetaToTarget, -1f, 1f);

            if (cos >= FrontCosThreshold)
            {
                return Straight;
            }

            if (cos <= BackCosThreshold)
            {
                return UTurn;
            }

            if (sin >= SideSinThreshold)
            {
                return Left;
            }

            if (sin <= -SideSinThreshold)
            {
                return Right;
            }

            return Straight;
        }
    }
}
