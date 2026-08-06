using System;
using System.Collections.Generic;
using CitySimulation.DTO;
using CitySimulation.GameObjects.Validation;
using UnityEngine;
using CitySimulation.GameObjects;

namespace CitySimulation.GameObjects.Entities
{
    [Serializable]
    public abstract class MapEntity
    {
        public string id;
        public MapCategory category;
        public string styleId;
        public Vector3 position;
        public Quaternion rotation;
        public GameObject gameObject;

        public virtual void ApplyTransform(Vector3 pos, Quaternion rot)
        {
            position = pos;
            rotation = rot;
            if (gameObject != null)
            {
                gameObject.transform.SetPositionAndRotation(pos, rot);
            }
        }

        public virtual MapEntityDTO ToDTO()
        {
            return new MapEntityDTO
            {
                id = id,
                category = category,
                styleId = styleId,
                position = position,
                rotation = rotation
            };
        }

        public virtual ValidationResult Validate(ObjectManager context = null)
        {
            var result = new ValidationResult();
            if (gameObject == null)
            {
                result.AddError($"Entity {id} has no GameObject instance.");
                return result;
            }

            var myCollider = gameObject.GetComponentInChildren<Collider>();
            if (myCollider == null)
            {
                return result;
            }

            var bounds = myCollider.bounds;
            var center = bounds.center;
            var halfExtents = bounds.extents;
            var rotation = myCollider.transform.rotation;

            // Broadphase overlap query; we only care if any other collider intersects
            var hits = Physics.OverlapBox(center, halfExtents, rotation, ~0, QueryTriggerInteraction.Ignore);
            foreach (var hit in hits)
            {
                if (hit == null || hit.transform.root == myCollider.transform.root)
                {
                    continue; // ignore self
                }

                result.AddError($"Entity {id} overlaps another collider.");
                break;
            }

            return result;
        }
    }

    [Serializable]
    public class VehicleEntity : MapEntity
    {
        public VehicleType vehicleType;
        public string currentRoadId;
        public string targetPointId;
        public GameDecisionStatus gameStatus;

        // Override to allow slight tolerance for side-by-side lanes (shrink collider extents)
        public override ValidationResult Validate(ObjectManager context = null)
        {
            var result = new ValidationResult();
            if (gameObject == null)
            {
                result.AddError($"Entity {id} has no GameObject instance.");
                return result;
            }

            var myCollider = gameObject.GetComponentInChildren<Collider>();
            if (myCollider == null)
            {
                return result;
            }

            var bounds = myCollider.bounds;
            var center = bounds.center;
            var halfExtents = bounds.extents;
            // Shrink X/Z laterally to tolerate adjacent lane; 
            const float lateralShrink = 0.45f; // 45% size keeps margin between lanes
            const float forwardClearance = 1.5f; // extra half-extent so total edge gap >= 3f
            halfExtents = new Vector3(halfExtents.x * lateralShrink, halfExtents.y, halfExtents.z + forwardClearance);
            var rotation = myCollider.transform.rotation;

            var hits = Physics.OverlapBox(center, halfExtents, rotation, ~0, QueryTriggerInteraction.Ignore);
            foreach (var hit in hits)
            {
                if (hit == null || hit.transform.root == myCollider.transform.root)
                {
                    continue;
                }

                result.AddError($"Entity {id} overlaps another collider.");
                break;
            }

            return result;
        }

        public override MapEntityDTO ToDTO()
        {
            return new VehicleDTO
            {
                id = id,
                category = category,
                styleId = styleId,
                position = position,
                rotation = rotation,
                vehicleType = vehicleType,
                currentRoadId = currentRoadId,
                targetPointId = targetPointId,
                gameStatus = gameStatus
            };
        }
    }

    [Serializable]
    public class TrafficLightEntity : MapEntity
    {
        public string currentGreenRoadId;
        public float timeInPhase;
        public List<string> controlledRoadIds = new();
        public GameDecisionStatus gameStatus;

        public override MapEntityDTO ToDTO()
        {
            return new TrafficLightDTO
            {
                id = id,
                category = category,
                styleId = styleId,
                position = position,
                rotation = rotation,
                currentGreenRoadId = currentGreenRoadId,
                timeInPhase = timeInPhase,
                controlledRoadIds = new List<string>(controlledRoadIds),
                gameStatus = gameStatus
            };
        }
    }

    [Serializable]
    public class RoadEntity : MapEntity
    {
        public List<Vector3> controlPoints = new();

        public override MapEntityDTO ToDTO()
        {
            return new RoadDTO
            {
                id = id,
                category = category,
                styleId = styleId,
                position = position,
                rotation = rotation,
                controlPoints = new List<Vector3>(controlPoints)
            };
        }

        // Roads skip collider-based overlap validation to allow drawing without colliders.
        public override ValidationResult Validate(ObjectManager context = null)
        {
            var result = new ValidationResult();
            if (gameObject == null)
            {
                result.AddError($"Road {id} has no GameObject instance.");
            }
            return result;
        }
    }

    [Serializable]
    public class BuildingEntity : MapEntity
    {
        public Vector3 size;

        public override MapEntityDTO ToDTO()
        {
            var savedSize = size;
            if (gameObject != null)
            {
                savedSize = gameObject.transform.localScale;
            }

            return new BuildingDTO
            {
                id = id,
                category = category,
                styleId = styleId,
                position = position,
                rotation = rotation,
                size = savedSize
            };
        }
    }

    [Serializable]
    public class TargetPointEntity : MapEntity
    {
        public override MapEntityDTO ToDTO()
        {
            return new TargetPointDTO
            {
                id = id,
                category = category,
                styleId = styleId,
                position = position,
                rotation = rotation
            };
        }
    }
}
