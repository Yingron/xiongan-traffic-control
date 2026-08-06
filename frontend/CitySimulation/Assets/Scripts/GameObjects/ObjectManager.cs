using System.Collections.Generic;
using System.Linq;
using CitySimulation.DTO;
using CitySimulation.GameObjects.Entities;
using CitySimulation.GameObjects.Validation;

namespace CitySimulation.GameObjects
{
    /// <summary>
    /// Runtime manager: create/destroy entities, operate on GameObjects directly, export DTO when saving.
    /// </summary>
    public class ObjectManager
    {
        private readonly Dictionary<string, MapEntity> _entitiesById = new();
        private readonly PrefabFactory _factory;

        [System.Serializable]
        public class MapSnapshot
        {
            public List<RoadDTO> roads = new();
            public List<TargetPointDTO> targetPoints = new();
            public List<BuildingDTO> buildings = new();
            public List<VehicleDTO> vehicles = new();
            public List<TrafficLightDTO> trafficLights = new();
        }

        public ObjectManager(PrefabFactory factory)
        {
            _factory = factory;
        }

        public MapEntity CreateObject(MapEntityDTO dto, bool need_validate = true)
        {
            if (string.IsNullOrEmpty(dto.id))
            {
                dto.id = System.Guid.NewGuid().ToString();
            }

            // Remove existing entity with same id
            DestroyObject(dto.id);

            // Validate before creation (via temp entity) and abort if invalid (unless disabled)
            var tempEntity = _factory.CreateEntity(dto);
            
            if (need_validate)
            {
                var validation = tempEntity.Validate(this);
                if (!validation.IsValid)
                {
                    // Log detailed validation errors to aid debugging (e.g. police prefab overlaps)
                    try
                    {
                        var id = dto?.id ?? "(unknown)";
                        var style = dto?.styleId ?? "(none)";
                        UnityEngine.Debug.LogWarning($"[ObjectManager] CreateObject validation failed for id={id} style={style}: {string.Join("; ", validation.errors)}");
                    }
                    catch { }

                    if (tempEntity.gameObject != null)
                    {
                        UnityEngine.Object.Destroy(tempEntity.gameObject);
                    }
                    return null;
                }
            }

            var entity = tempEntity;
            _entitiesById[entity.id] = entity;

            return entity;
        }

        public void DestroyObject(string id)
        {
            if (!_entitiesById.TryGetValue(id, out var entity))
            {
                return;
            }
            bool roadRemoved = entity is RoadEntity;
            bool targetPointRemoved = entity is TargetPointEntity;
            if (entity.gameObject != null)
            {
                UnityEngine.Object.Destroy(entity.gameObject);
            }
            _entitiesById.Remove(id);

            // check currentRoadId
            if (roadRemoved)
            {
                RefreshVehicleCurrentRoadIds();
            }

            if (targetPointRemoved)
            {
                RefreshVehicleTargetPointIds(id);
            }
        }

        public MapEntity GetEntity(string id)
        {
            _entitiesById.TryGetValue(id, out var e);
            return e;
        }

        // Export grouped by concrete type to preserve subtype fields (e.g., road control points)
        public MapSnapshot ExportAll()
        {
            var snap = new MapSnapshot();
            foreach (var e in _entitiesById.Values)
            {
                switch (e)
                {
                    case RoadEntity road:
                        snap.roads.Add(road.ToDTO() as RoadDTO);
                        break;
                    case BuildingEntity building:
                        snap.buildings.Add(building.ToDTO() as BuildingDTO);
                        break;
                    case TargetPointEntity targetPoint:
                        snap.targetPoints.Add(targetPoint.ToDTO() as TargetPointDTO);
                        break;
                    case VehicleEntity vehicle:
                        snap.vehicles.Add(vehicle.ToDTO() as VehicleDTO);
                        break;
                    case TrafficLightEntity traffic:
                        snap.trafficLights.Add(traffic.ToDTO() as TrafficLightDTO);
                        break;
                }
            }
            return snap;
        }


        public void ImportAll(MapSnapshot snap)
        {
            foreach (var kv in _entitiesById.Keys.ToList())
            {
                DestroyObject(kv);
            }

            if (snap == null)
            {
                return;
            }

            if (snap.roads != null)
            {
                foreach (var dto in snap.roads)
                {
                    // Ensure dto with guid
                    if (string.IsNullOrEmpty(dto.id)) dto.id = System.Guid.NewGuid().ToString();
                    // Ensure category matches list type
                    dto.category = MapCategory.Road;
                    // Unity's JsonUtility will assign default values for missing struct fields when
                    // deserializing. For a Quaternion this means a missing or zeroed value will
                    // become (0, 0, 0, 0), which is not a valid "identity" rotation. Therefore
                    // we explicitly detect a zero quaternion and replace it with
                    // `Quaternion.identity` (0, 0, 0, 1) to represent no rotation.
                    if (dto.rotation.x == 0f && dto.rotation.y == 0f && dto.rotation.z == 0f && dto.rotation.w == 0f)
                    {
                        dto.rotation = UnityEngine.Quaternion.identity;
                    }
                    CreateObject(dto, need_validate: false);
                }
            }
            if (snap.buildings != null)
            {
                foreach (var dto in snap.buildings)
                {
                    if (string.IsNullOrEmpty(dto.id)) dto.id = System.Guid.NewGuid().ToString();
                    dto.category = MapCategory.Building;
                    if (dto.rotation.x == 0f && dto.rotation.y == 0f && dto.rotation.z == 0f && dto.rotation.w == 0f)
                    {
                        dto.rotation = UnityEngine.Quaternion.identity;
                    }
                    CreateObject(dto, need_validate: false);
                }
            }
            if (snap.targetPoints != null)
            {
                foreach (var dto in snap.targetPoints)
                {
                    if (string.IsNullOrEmpty(dto.id)) dto.id = System.Guid.NewGuid().ToString();
                    dto.category = MapCategory.TargetPoint;
                    if (dto.rotation.x == 0f && dto.rotation.y == 0f && dto.rotation.z == 0f && dto.rotation.w == 0f)
                    {
                        dto.rotation = UnityEngine.Quaternion.identity;
                    }
                    CreateObject(dto, need_validate: false);
                }
            }
            if (snap.vehicles != null)
            {
                foreach (var dto in snap.vehicles)
                {
                    if (string.IsNullOrEmpty(dto.id)) dto.id = System.Guid.NewGuid().ToString();
                    dto.category = MapCategory.Vehicle;
                    if (dto.rotation.x == 0f && dto.rotation.y == 0f && dto.rotation.z == 0f && dto.rotation.w == 0f)
                    {
                        dto.rotation = UnityEngine.Quaternion.identity;
                    }
                    CreateObject(dto, need_validate: false);
                }
            }
            if (snap.trafficLights != null)
            {
                foreach (var dto in snap.trafficLights)
                {
                    if (string.IsNullOrEmpty(dto.id)) dto.id = System.Guid.NewGuid().ToString();
                    dto.category = MapCategory.TrafficLight;
                    if (dto.rotation.x == 0f && dto.rotation.y == 0f && dto.rotation.z == 0f && dto.rotation.w == 0f)
                    {
                        dto.rotation = UnityEngine.Quaternion.identity;
                    }
                    CreateObject(dto, need_validate: false);
                }
            }
        }

        // Expose enumerable for validation contexts and tools
        public IEnumerable<MapEntity> GetAllEntities()
        {
            return _entitiesById.Values;
        }

        // Find an entity by a GameObject hit (compares against the root transform to tolerate child hits)
        public MapEntity FindByGameObject(UnityEngine.GameObject go)
        {
            if (go == null)
            {
                return null;
            }
            var root = go.transform.root;
            foreach (var entity in _entitiesById.Values)
            {
                if (entity?.gameObject == null)
                {
                    continue;
                }
                if (entity.gameObject.transform == root)
                {
                    return entity;
                }
            }
            return null;
        }

        public ValidationResult Validate()
        {
            var result = new ValidationResult();
            foreach (var entity in _entitiesById.Values)
            {
                result.Merge(entity.Validate());
            }
            return result;
        }

        private void RefreshVehicleCurrentRoadIds()
        {
            foreach (var entity in _entitiesById.Values)
            {
                if (entity is VehicleEntity vehicle)
                {
                    if (!string.IsNullOrEmpty(vehicle.currentRoadId) && !HasRoad(vehicle.currentRoadId))
                    {
                        vehicle.currentRoadId = null;
                    }
                }
            }
        }

        private void RefreshVehicleTargetPointIds(string removedTargetPointId)
        {
            if (string.IsNullOrEmpty(removedTargetPointId))
            {
                return;
            }

            foreach (var entity in _entitiesById.Values)
            {
                if (entity is not VehicleEntity vehicle)
                {
                    continue;
                }

                if (vehicle.targetPointId == removedTargetPointId)
                {
                    vehicle.targetPointId = null;
                }
            }
        }

        bool HasRoad(string roadId)
        {
            if (string.IsNullOrEmpty(roadId))
            {
                return false;
            }

            foreach (var entity in _entitiesById.Values)
            {
                if (entity is RoadEntity road && road.id == roadId)
                {
                    return true;
                }
            }

            return false;
        }
    }
}
