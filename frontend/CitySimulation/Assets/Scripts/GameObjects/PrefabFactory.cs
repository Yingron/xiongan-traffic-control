using System.Collections.Generic;
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
        private readonly Dictionary<int, Material> _vehiclePaintMaterials = new Dictionary<int, Material>();
        private Material _vehicleCabinMaterial;
        private Material _vehicleWheelMaterial;
        private Material _vehicleGlassMaterial;
        private Material _vehicleHeadLampMaterial;
        private Material _vehicleTailLampMaterial;
        private Material _vehiclePoliceRedMaterial;
        private Material _vehiclePoliceBlueMaterial;

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
            var vehicleDto = dto as VehicleDTO;
            var vehicleType = vehicleDto?.vehicleType ?? VehicleType.Normal;
            var go = TryLoad(PathFor(dto)) ?? TryLoad(dto.styleId) ?? CreateFallback(dto.category, dto.id, vehicleType);
            // Some legacy Resources vehicle prefabs retain only a missing mesh
            // reference.  They instantiate successfully but render as a zero-size
            // object, which makes traffic appear as plain boxes or disappear.
            if (dto.category == MapCategory.Vehicle && !HasUsableVehicleRenderer(go))
            {
                if (go != null)
                {
                    Object.Destroy(go);
                }
                go = CreateVehicleFallback(dto.id, vehicleType);
            }
            go.name = string.IsNullOrEmpty(dto.styleId) ? $"{dto.category}_{dto.id}" : dto.styleId;
            var visualPosition = dto.position;
            if (dto.category == MapCategory.TrafficLight)
            {
                // The exported y=5 denotes signal height in legacy data.  The
                // procedural animator already creates a 4 m pole from its root,
                // so use the road surface as the visual anchor to avoid floating
                // signals in the 30-junction Unity scene.
                visualPosition.y = 0f;
            }
            go.transform.SetPositionAndRotation(visualPosition, dto.rotation);

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

                // Resources/TrafficLight/Empty_TrafficLight is deliberately an
                // empty anchor prefab.  AddComponent does not reliably invoke
                // the editor lifecycle when maps are imported in batch/standalone
                // mode, so construct the visible poles and bulbs explicitly.
                // Existing authored signal prefabs are kept intact.
                if (animator.transform.childCount == 0)
                {
                    animator.RebuildChildren();
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
        private GameObject CreateFallback(MapCategory category, string entityId = null, VehicleType vehicleType = VehicleType.Normal)
        {
            if (category == MapCategory.Vehicle)
            {
                return CreateVehicleFallback(entityId, vehicleType);
            }

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

        private static bool HasUsableVehicleRenderer(GameObject go)
        {
            if (go == null) return false;
            foreach (var renderer in go.GetComponentsInChildren<Renderer>(true))
            {
                if (renderer.bounds.size.sqrMagnitude > 0.0001f)
                {
                    return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Builds a lightweight but readable traffic vehicle when a legacy prefab
        /// cannot render.  The id selects a stable appearance, so object pooling
        /// does not make a car change colour or body type during a simulation.
        /// </summary>
        private GameObject CreateVehicleFallback(string entityId, VehicleType vehicleType)
        {
            var variant = GetVehicleVariant(entityId);
            var emergency = vehicleType == VehicleType.Emergency;
            var profile = GetVehicleProfile(variant, emergency);
            var paint = emergency ? new Color(0.92f, 0.94f, 0.98f) : GetVehiclePaint(variant);

            var root = new GameObject(emergency ? "ProceduralEmergencyVehicle" : $"ProceduralVehicle_{profile.name}");
            CreateVehiclePart(root.transform, PrimitiveType.Cube, "Body",
                new Vector3(0f, profile.bodyY, 0f), new Vector3(profile.width, profile.bodyHeight, profile.length), GetVehiclePaintMaterial(paint));
            CreateVehiclePart(root.transform, PrimitiveType.Cube, "Cabin",
                new Vector3(0f, profile.cabinY, profile.cabinZ), new Vector3(profile.cabinWidth, profile.cabinHeight, profile.cabinLength), GetVehicleCabinMaterial());

            // Dark windscreen, lamps and wheels make the primitive geometry read
            // as a vehicle from the overview camera rather than a plain cuboid.
            CreateVehiclePart(root.transform, PrimitiveType.Cube, "Windshield",
                new Vector3(0f, profile.cabinY + profile.cabinHeight * 0.07f, profile.cabinZ + profile.cabinLength * 0.51f),
                new Vector3(profile.cabinWidth * 0.78f, profile.cabinHeight * 0.68f, 0.035f), GetVehicleGlassMaterial());

            var lampX = profile.width * 0.31f;
            var frontZ = profile.length * 0.505f;
            var rearZ = -profile.length * 0.505f;
            CreateVehiclePart(root.transform, PrimitiveType.Sphere, "HeadLampLeft", new Vector3(-lampX, profile.bodyY + 0.04f, frontZ),
                new Vector3(0.22f, 0.16f, 0.10f), GetVehicleHeadLampMaterial());
            CreateVehiclePart(root.transform, PrimitiveType.Sphere, "HeadLampRight", new Vector3(lampX, profile.bodyY + 0.04f, frontZ),
                new Vector3(0.22f, 0.16f, 0.10f), GetVehicleHeadLampMaterial());
            CreateVehiclePart(root.transform, PrimitiveType.Sphere, "TailLampLeft", new Vector3(-lampX, profile.bodyY + 0.04f, rearZ),
                new Vector3(0.22f, 0.16f, 0.10f), GetVehicleTailLampMaterial());
            CreateVehiclePart(root.transform, PrimitiveType.Sphere, "TailLampRight", new Vector3(lampX, profile.bodyY + 0.04f, rearZ),
                new Vector3(0.22f, 0.16f, 0.10f), GetVehicleTailLampMaterial());

            var wheelPositions = new[]
            {
                new Vector3(-profile.width * 0.55f, 0.36f, -profile.length * 0.30f), new Vector3(profile.width * 0.55f, 0.36f, -profile.length * 0.30f),
                new Vector3(-profile.width * 0.55f, 0.36f, profile.length * 0.30f), new Vector3(profile.width * 0.55f, 0.36f, profile.length * 0.30f),
            };
            foreach (var position in wheelPositions)
            {
                var wheel = CreateVehiclePart(root.transform, PrimitiveType.Cylinder, "Wheel", position,
                    new Vector3(profile.wheelRadius, 0.18f, profile.wheelRadius), GetVehicleWheelMaterial());
                wheel.transform.localRotation = Quaternion.Euler(0f, 0f, 90f);
            }

            if (emergency)
            {
                CreateVehiclePart(root.transform, PrimitiveType.Cube, "PoliceLightBlue",
                    new Vector3(-profile.cabinWidth * 0.24f, profile.cabinY + profile.cabinHeight * 0.62f, profile.cabinZ),
                    new Vector3(profile.cabinWidth * 0.32f, 0.16f, 0.35f), GetVehiclePoliceBlueMaterial());
                CreateVehiclePart(root.transform, PrimitiveType.Cube, "PoliceLightRed",
                    new Vector3(profile.cabinWidth * 0.24f, profile.cabinY + profile.cabinHeight * 0.62f, profile.cabinZ),
                    new Vector3(profile.cabinWidth * 0.32f, 0.16f, 0.35f), GetVehiclePoliceRedMaterial());
            }
            return root;
        }

        private static int GetVehicleVariant(string entityId)
        {
            unchecked
            {
                var hash = 17;
                foreach (var character in entityId ?? string.Empty)
                {
                    hash = hash * 31 + character;
                }
                return (hash & 0x7fffffff) % 4;
            }
        }

        private static VehicleProfile GetVehicleProfile(int variant, bool emergency)
        {
            if (emergency) return new VehicleProfile("Emergency", 1.95f, 4.55f, 0.78f, 0.64f, 0.30f, 1.67f, 2.05f, 0.64f, 0.39f);
            return variant switch
            {
                0 => new VehicleProfile("Compact", 1.68f, 3.65f, 0.64f, 0.60f, 0.45f, 1.38f, 1.55f, 0.58f, 0.34f),
                1 => new VehicleProfile("Sedan", 1.84f, 4.25f, 0.72f, 0.62f, 0.25f, 1.56f, 2.02f, 0.62f, 0.38f),
                2 => new VehicleProfile("SUV", 2.04f, 4.35f, 0.84f, 0.68f, 0.16f, 1.77f, 2.04f, 0.70f, 0.43f),
                _ => new VehicleProfile("Van", 2.08f, 4.82f, 0.92f, 0.72f, 0.05f, 1.86f, 2.52f, 0.78f, 0.44f),
            };
        }

        private static Color GetVehiclePaint(int variant)
        {
            return variant switch
            {
                0 => new Color(0.08f, 0.42f, 0.88f),
                1 => new Color(0.90f, 0.22f, 0.12f),
                2 => new Color(0.10f, 0.63f, 0.36f),
                _ => new Color(0.96f, 0.56f, 0.08f),
            };
        }

        private readonly struct VehicleProfile
        {
            public readonly string name;
            public readonly float width, length, bodyHeight, bodyY, cabinZ, cabinWidth, cabinLength, cabinHeight, wheelRadius;
            public VehicleProfile(string name, float width, float length, float bodyHeight, float bodyY, float cabinZ, float cabinWidth, float cabinLength, float cabinHeight, float wheelRadius)
            {
                this.name = name; this.width = width; this.length = length; this.bodyHeight = bodyHeight; this.bodyY = bodyY;
                this.cabinZ = cabinZ; this.cabinWidth = cabinWidth; this.cabinLength = cabinLength; this.cabinHeight = cabinHeight; this.wheelRadius = wheelRadius;
            }
            public float cabinY => bodyY + bodyHeight * 0.5f + cabinHeight * 0.48f;
        }

        private static GameObject CreateVehiclePart(Transform parent, PrimitiveType primitive, string partName,
            Vector3 localPosition, Vector3 localScale, Material material)
        {
            var part = GameObject.CreatePrimitive(primitive);
            part.name = partName;
            part.transform.SetParent(parent, false);
            part.transform.localPosition = localPosition;
            part.transform.localScale = localScale;
            var renderer = part.GetComponent<Renderer>();
            if (renderer != null) renderer.sharedMaterial = material;
            var collider = part.GetComponent<Collider>();
            if (collider != null) Object.Destroy(collider);
            return part;
        }

        private Material GetVehiclePaintMaterial(Color color)
        {
            var c = (Color32)color;
            var key = (c.r << 16) | (c.g << 8) | c.b;
            if (!_vehiclePaintMaterials.TryGetValue(key, out var material))
            {
                material = CreateVehicleMaterial($"RuntimeVehiclePaint_{key:X6}", color);
                _vehiclePaintMaterials.Add(key, material);
            }
            return material;
        }

        private Material GetVehicleCabinMaterial()
        {
            if (_vehicleCabinMaterial == null) _vehicleCabinMaterial = CreateVehicleMaterial("RuntimeVehicleCabin", new Color(0.72f, 0.9f, 1f));
            return _vehicleCabinMaterial;
        }

        private Material GetVehicleWheelMaterial()
        {
            if (_vehicleWheelMaterial == null) _vehicleWheelMaterial = CreateVehicleMaterial("RuntimeVehicleWheel", new Color(0.05f, 0.05f, 0.05f));
            return _vehicleWheelMaterial;
        }

        private Material GetVehicleGlassMaterial()
        {
            if (_vehicleGlassMaterial == null) _vehicleGlassMaterial = CreateVehicleMaterial("RuntimeVehicleGlass", new Color(0.08f, 0.20f, 0.29f));
            return _vehicleGlassMaterial;
        }

        private Material GetVehicleHeadLampMaterial()
        {
            if (_vehicleHeadLampMaterial == null) _vehicleHeadLampMaterial = CreateVehicleMaterial("RuntimeVehicleHeadLamp", new Color(1f, 0.90f, 0.52f));
            return _vehicleHeadLampMaterial;
        }

        private Material GetVehicleTailLampMaterial()
        {
            if (_vehicleTailLampMaterial == null) _vehicleTailLampMaterial = CreateVehicleMaterial("RuntimeVehicleTailLamp", new Color(0.92f, 0.06f, 0.04f));
            return _vehicleTailLampMaterial;
        }

        private Material GetVehiclePoliceRedMaterial()
        {
            if (_vehiclePoliceRedMaterial == null) _vehiclePoliceRedMaterial = CreateVehicleMaterial("RuntimePoliceRed", new Color(0.95f, 0.04f, 0.04f));
            return _vehiclePoliceRedMaterial;
        }

        private Material GetVehiclePoliceBlueMaterial()
        {
            if (_vehiclePoliceBlueMaterial == null) _vehiclePoliceBlueMaterial = CreateVehicleMaterial("RuntimePoliceBlue", new Color(0.02f, 0.34f, 0.95f));
            return _vehiclePoliceBlueMaterial;
        }

        private static Material CreateVehicleMaterial(string materialName, Color color)
        {
            var shader = Shader.Find("Standard") ?? Shader.Find("Sprites/Default");
            var material = new Material(shader) { name = materialName, color = color };
            return material;
        }
    }
}
