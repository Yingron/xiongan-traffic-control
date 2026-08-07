using CitySimulation.DTO;
using CitySimulation.GameObjects.Entities;
using UnityEngine;

namespace CitySimulation.GameObjects
{
    /// <summary>
    /// Creates entities and their GameObject instances. Prefers Resources.Load(category/styleId); falls back to primitives.
    /// </summary>
    public class PrefabFactory
    {
        private string PathFor(MapEntityDTO dto)
        {
            if (string.IsNullOrEmpty(dto.styleId))
            {
                return null;
            }
            return $"{dto.category}/{dto.styleId}";
        }

        public MapEntity CreateEntity(MapEntityDTO dto)
        {
            var go = TryLoad(PathFor(dto)) ?? TryLoad(dto.styleId) ?? CreateFallback(dto.category);
            go.name = string.IsNullOrEmpty(dto.styleId) ? $"{dto.category}_{dto.id}" : dto.styleId;
            go.transform.SetPositionAndRotation(dto.position, dto.rotation);

            // Optional orientation fix: rotate along X to lay road-aligned assets flat if needed
            if (dto.category == MapCategory.Road)
            {
                go.transform.Rotate(90f, 0f, 0f, Space.Self);
            }

            MapEntity entity = dto.category switch
            {
                MapCategory.Road => new RoadEntity
                {
                    id = dto.id,
                    category = dto.category,
                    styleId = dto.styleId,
                    position = dto.position,
                    rotation = dto.rotation,
                    controlPoints = (dto as RoadDTO)?.controlPoints ?? new System.Collections.Generic.List<Vector3>()
                },
                MapCategory.Building => new BuildingEntity
                {
                    id = dto.id,
                    category = dto.category,
                    styleId = dto.styleId,
                    position = dto.position,
                    rotation = dto.rotation,
                    size = ResolveBuildingSize(dto as BuildingDTO)
                },
                MapCategory.TargetPoint => new TargetPointEntity
                {
                    id = dto.id,
                    category = dto.category,
                    styleId = dto.styleId,
                    position = dto.position,
                    rotation = dto.rotation
                },
                MapCategory.Vehicle => new VehicleEntity
                {
                    id = dto.id,
                    category = dto.category,
                    styleId = dto.styleId,
                    position = dto.position,
                    rotation = dto.rotation,
                    vehicleType = (dto as VehicleDTO)?.vehicleType ?? VehicleType.Normal,
                    currentRoadId = (dto as VehicleDTO)?.currentRoadId,
                    targetPointId = (dto as VehicleDTO)?.targetPointId,
                    gameStatus = (dto as VehicleDTO)?.gameStatus ?? GameDecisionStatus.NoDecisionNeeded
                },
                MapCategory.TrafficLight => new TrafficLightEntity
                {
                    id = dto.id,
                    category = dto.category,
                    styleId = dto.styleId,
                    position = dto.position,
                    rotation = dto.rotation,
                    currentGreenRoadId = (dto as TrafficLightDTO)?.currentGreenRoadId,
                    timeInPhase = (dto as TrafficLightDTO)?.timeInPhase ?? 0f,
                    controlledRoadIds = (dto as TrafficLightDTO)?.controlledRoadIds ?? new System.Collections.Generic.List<string>(),
                    gameStatus = (dto as TrafficLightDTO)?.gameStatus ?? GameDecisionStatus.NoDecisionNeeded
                },
                _ => new BuildingEntity
                {
                    id = dto.id,
                    category = dto.category,
                    styleId = dto.styleId,
                    position = dto.position,
                    rotation = dto.rotation
                }
            };

            entity.gameObject = go;

            if (entity is BuildingEntity building)
            {
                ApplyBuildingSize(go, building.size);
            }

            // Post-process: apply control points to visual components (LineRenderer or custom renderer)
            if (entity is RoadEntity road)
            {
                ApplyRoadVisual(go, road.controlPoints);
            }

            // Post-process: 为信号灯挂载4相位动画器
            if (entity is TrafficLightEntity tlEntity)
            {
                // 注意: JSON 坐标约定为 (x=网格列, y=高度, z=网格行)
                // 直接映射到 Unity (X, Y, Z)。交通灯 y=5 是灯柱高度，无需修改。

                var animator = go.GetComponent<TrafficLightAnimator>();
                if (animator == null)
                {
                    animator = go.AddComponent<TrafficLightAnimator>();
                }
            }

            return entity;
        }

        private void ApplyRoadVisual(GameObject go, System.Collections.Generic.List<Vector3> controlPoints)
        {
            if (go == null)
            {
                return;
            }

            // Fallback: plain LineRenderer
            var lr = go.GetComponent<LineRenderer>();
            if (lr != null && controlPoints != null && controlPoints.Count >= 2)
            {
                lr.useWorldSpace = true;
                lr.positionCount = controlPoints.Count;
                var arr = new Vector3[controlPoints.Count];
                for (int i = 0; i < controlPoints.Count; i++)
                {
                    var p = controlPoints[i];
                    arr[i] = new Vector3(p.x, 0f, p.z); // lock to ground
                }
                lr.SetPositions(arr);
            }
        }

        private static Vector3 ResolveBuildingSize(BuildingDTO dto)
        {
            if (dto == null)
            {
                return Vector3.zero;
            }

            return dto.size;
        }

        private static void ApplyBuildingSize(GameObject go, Vector3 size)
        {
            if (go == null)
            {
                return;
            }

            if (size.x <= 0f || size.y <= 0f || size.z <= 0f)
            {
                return;
            }

            go.transform.localScale = size;
        }

        private GameObject TryLoad(string key)
        {
            if (string.IsNullOrEmpty(key))
            {
                return null;
            }

            var prefab = Resources.Load<GameObject>(key);
            if (prefab == null)
            {
                Debug.LogWarning($"[PrefabFactory] Resources.Load failed for '{key}'");
                return null;
            }

            return GameObject.Instantiate(prefab);
        }

        // create a simple substitution
        private GameObject CreateFallback(MapCategory category)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            if (category == MapCategory.Road)
            {
                go.transform.localScale = new Vector3(5f, 0.2f, 1f);
            }
            else if (category == MapCategory.Building)
            {
                go.transform.localScale = new Vector3(1f, 2f, 1f);
                var renderer = go.GetComponent<Renderer>();
                if (renderer != null)
                {
                    renderer.material.color = new Color(0.6f, 0.6f, 0.6f, 1f);
                }
            }
            return go;
        }
    }
}
