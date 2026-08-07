using System.Collections.Generic;

namespace CitySimulation.Runtime.Services.Traffic
{
    public sealed class TurningLock
    {
        readonly string roadAId;
        readonly string roadBId;

        readonly RoadSemaphore roadALock = new();
        readonly RoadSemaphore roadBLock = new();
        string exclusiveVehicleId;

        public TurningLock(string roadAId, string roadBId)
        {
            this.roadAId = roadAId;
            this.roadBId = roadBId;
        }
        // for Straight / Right / Left / UTurn
        public bool CanEnter(string roadId, int directionSign)
        {
            if (!string.IsNullOrEmpty(exclusiveVehicleId))
            {
                return false;
            }

            var semaphore = GetRoadSemaphore(roadId);
            if (semaphore == null)
            {
                return true;
            }

            return semaphore.CanEnter(directionSign);
        }

        // for Left / UTurn
        public bool TryAcquire(string roadId, int directionSign, string vehicleId)
        {
            if (!string.IsNullOrEmpty(exclusiveVehicleId)
                && !string.Equals(exclusiveVehicleId, vehicleId, System.StringComparison.Ordinal))
            {
                return false;
            }

            var semaphore = GetRoadSemaphore(roadId);
            if (semaphore == null)
            {
                return false;
            }

            return semaphore.TryAcquire(directionSign, vehicleId);
        }

        // Atomic UTurn owns the whole intersection until both internal left
        // phases complete. The backend still observes one action.
        public bool TryAcquireExclusive(string vehicleId)
        {
            if (string.IsNullOrEmpty(vehicleId))
            {
                return false;
            }

            if (string.Equals(exclusiveVehicleId, vehicleId, System.StringComparison.Ordinal))
            {
                return true;
            }

            if (!string.IsNullOrEmpty(exclusiveVehicleId)
                || !roadALock.IsEmptyOrOwnedBy(vehicleId)
                || !roadBLock.IsEmptyOrOwnedBy(vehicleId))
            {
                return false;
            }

            exclusiveVehicleId = vehicleId;
            return true;
        }

        public void Release(string roadId, int directionSign, string vehicleId)
        {
            var semaphore = GetRoadSemaphore(roadId);
            semaphore?.Release(directionSign, vehicleId);
        }

        public void ReleaseAll(string vehicleId)
        {
            if (string.IsNullOrEmpty(vehicleId))
            {
                return;
            }

            roadALock.ReleaseAll(vehicleId);
            roadBLock.ReleaseAll(vehicleId);
            if (string.Equals(exclusiveVehicleId, vehicleId, System.StringComparison.Ordinal))
            {
                exclusiveVehicleId = null;
            }
        }

        RoadSemaphore GetRoadSemaphore(string roadId)
        {
            if (string.Equals(roadId, roadAId, System.StringComparison.Ordinal))
            {
                return roadALock;
            }

            if (string.Equals(roadId, roadBId, System.StringComparison.Ordinal))
            {
                return roadBLock;
            }

            return null;
        }

        sealed class RoadSemaphore
        {
            // Direction sign is computed by taking the dot product between:
            // 1) the road axis at the intersection, and
            // 2) the vehicle's offset relative to the traffic light.
            // If dot >= 0, directionSign is treated as the positive direction
            // and this vehicle is tracked in directionPositiveVehicleIds.
            // If dot < 0, directionSign is treated as the negative direction
            // and this vehicle is tracked in directionNegativeVehicleIds.
            readonly HashSet<string> directionPositiveVehicleIds = new();
            readonly HashSet<string> directionNegativeVehicleIds = new();

            public bool IsEmptyOrOwnedBy(string vehicleId)
            {
                foreach (string id in directionPositiveVehicleIds)
                {
                    if (!string.Equals(id, vehicleId, System.StringComparison.Ordinal))
                    {
                        return false;
                    }
                }
                foreach (string id in directionNegativeVehicleIds)
                {
                    if (!string.Equals(id, vehicleId, System.StringComparison.Ordinal))
                    {
                        return false;
                    }
                }
                return true;
            }

            public bool CanEnter(int directionSign)
            {
                if (directionSign >= 0)
                {
                    return directionNegativeVehicleIds.Count == 0;
                }

                return directionPositiveVehicleIds.Count == 0;
            }

            public bool TryAcquire(int directionSign, string vehicleId)
            {
                if (string.IsNullOrEmpty(vehicleId))
                {
                    return false;
                }

                // If this vehicle already holds the lock (in either direction),
                // don't try to re-acquire — treat as success.
                if (directionPositiveVehicleIds.Contains(vehicleId) || directionNegativeVehicleIds.Contains(vehicleId))
                {
                    return true;
                }

                if (!CanEnter(directionSign))
                {
                    return false;
                }

                if (directionSign >= 0)
                {
                    directionPositiveVehicleIds.Add(vehicleId);
                }
                else
                {
                    directionNegativeVehicleIds.Add(vehicleId);
                }

                return true;
            }

            public void Release(int directionSign, string vehicleId)
            {
                if (string.IsNullOrEmpty(vehicleId))
                {
                    return;
                }

                if (directionSign >= 0)
                {
                    directionPositiveVehicleIds.Remove(vehicleId);
                }
                else
                {
                    directionNegativeVehicleIds.Remove(vehicleId);
                }
            }

            public void ReleaseAll(string vehicleId)
            {
                if (string.IsNullOrEmpty(vehicleId))
                {
                    return;
                }

                directionPositiveVehicleIds.Remove(vehicleId);
                directionNegativeVehicleIds.Remove(vehicleId);
            }
        }
    }
}
