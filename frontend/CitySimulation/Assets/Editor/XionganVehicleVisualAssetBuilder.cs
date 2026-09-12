using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace CitySimulation.EditorTools
{
    /// <summary>
    /// Builds the reusable low-poly vehicle used by the SUMO visualization layer.
    /// The mesh uses +Z as the vehicle nose, +Y as up and X as vehicle width.
    /// Generated files live under tool-owned paths, so repeated execution updates
    /// the same assets without creating duplicate materials or prefabs.
    /// </summary>
    public static class XionganVehicleVisualAssetBuilder
    {
        public const string MenuPath = "Tools/Xiongan/Build Vehicle Visual Assets";
        public const string GeneratedRoot = "Assets/Xiongan/VehicleVisual/Generated";
        public const string MeshPath = GeneratedRoot + "/XionganLowPolyCarMesh.asset";
        public const string BodyMaterialPath = GeneratedRoot + "/XionganCarBody.mat";
        public const string DarkMaterialPath = GeneratedRoot + "/XionganCarDark.mat";
        public const string FrontLightMaterialPath = GeneratedRoot + "/XionganCarFrontLight.mat";
        public const string RearLightMaterialPath = GeneratedRoot + "/XionganCarRearLight.mat";
        public const string PrefabPath = "Assets/Resources/Vehicle/XionganLowPolyCar.prefab";

        [MenuItem(MenuPath)]
        public static void BuildVehicleVisualAssets()
        {
            EnsureFolder("Assets", "Xiongan");
            EnsureFolder("Assets/Xiongan", "VehicleVisual");
            EnsureFolder("Assets/Xiongan/VehicleVisual", "Generated");
            EnsureFolder("Assets", "Resources");
            EnsureFolder("Assets/Resources", "Vehicle");

            var mesh = CreateVehicleMesh();
            var persistentMesh = SaveOrUpdateMesh(mesh, MeshPath);

            var body = SaveOrUpdateMaterial(
                BodyMaterialPath, "XionganCarBody", new Color(0.055f, 0.33f, 0.78f, 1f), 0.38f, 0.48f);
            var dark = SaveOrUpdateMaterial(
                DarkMaterialPath, "XionganCarDark", new Color(0.018f, 0.028f, 0.045f, 1f), 0.18f, 0.12f);
            var frontLight = SaveOrUpdateMaterial(
                FrontLightMaterialPath, "XionganCarFrontLight", new Color(1f, 0.83f, 0.35f, 1f), 0.05f, 0.28f);
            var rearLight = SaveOrUpdateMaterial(
                RearLightMaterialPath, "XionganCarRearLight", new Color(0.86f, 0.025f, 0.018f, 1f), 0.05f, 0.22f);

            var root = new GameObject("XionganLowPolyCar");
            try
            {
                // TraCI getPosition is passed through unchanged and represents the
                // front-bumper center. Keep the vehicle root at that true position;
                // offset only the centered visual by half the 4.4 m display length.
                var offset = new GameObject("VisualOffset").transform;
                offset.SetParent(root.transform, false);
                offset.localPosition = new Vector3(0f, 0f, -2.2f);

                var visual = new GameObject("VehicleVisual");
                visual.transform.SetParent(offset, false);
                var filter = visual.AddComponent<MeshFilter>();
                filter.sharedMesh = persistentMesh;
                var renderer = visual.AddComponent<MeshRenderer>();
                renderer.sharedMaterials = new[] { body, dark, frontLight, rearLight };
                renderer.shadowCastingMode = ShadowCastingMode.On;
                renderer.receiveShadows = true;
                renderer.lightProbeUsage = LightProbeUsage.Off;
                renderer.reflectionProbeUsage = ReflectionProbeUsage.Off;

                PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
            }
            finally
            {
                Object.DestroyImmediate(root);
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            var triangleCount = persistentMesh.triangles.Length / 3;
            Debug.Log(
                $"[VehicleVisualBuilder] Built {PrefabPath}; vertices={persistentMesh.vertexCount}; " +
                $"triangles={triangleCount}; bounds={persistentMesh.bounds.size}; subMeshes={persistentMesh.subMeshCount}");
        }

        static Mesh CreateVehicleMesh()
        {
            var builder = new MeshBuilder(4);

            // Body and a wedge-shaped roof/cabin. Display dimensions are a documented
            // visual approximation only: 1.9 m wide, 4.4 m long and 1.55 m high.
            builder.AddBox(new Vector3(-0.95f, 0.28f, -2.2f), new Vector3(0.95f, 0.94f, 2.2f), 0);
            builder.AddWedgeCabin(
                bottomRearZ: -1.02f, bottomFrontZ: 1.18f,
                topRearZ: -0.58f, topFrontZ: 0.70f,
                bottomY: 0.90f, topY: 1.55f,
                bottomHalfWidth: 0.80f, topHalfWidth: 0.66f,
                subMesh: 0);

            // Dark glazing panels sit just above the cabin shell.
            builder.AddQuad(
                new Vector3(-0.665f, 1.535f, 0.715f), new Vector3(0.665f, 1.535f, 0.715f),
                new Vector3(0.805f, 0.915f, 1.195f), new Vector3(-0.805f, 0.915f, 1.195f), 1);
            builder.AddQuad(
                new Vector3(0.665f, 1.535f, -0.595f), new Vector3(-0.665f, 1.535f, -0.595f),
                new Vector3(-0.805f, 0.915f, -1.035f), new Vector3(0.805f, 0.915f, -1.035f), 1);
            builder.AddQuad(
                new Vector3(-0.812f, 0.94f, -0.87f), new Vector3(-0.675f, 1.51f, -0.52f),
                new Vector3(-0.675f, 1.51f, 0.60f), new Vector3(-0.812f, 0.94f, 1.02f), 1);
            builder.AddQuad(
                new Vector3(0.812f, 0.94f, 1.02f), new Vector3(0.675f, 1.51f, 0.60f),
                new Vector3(0.675f, 1.51f, -0.52f), new Vector3(0.812f, 0.94f, -0.87f), 1);

            // Four low-segment wheels, sharing the dark material.
            var wheelCenters = new[]
            {
                new Vector3(-0.99f, 0.42f, -1.38f), new Vector3(0.99f, 0.42f, -1.38f),
                new Vector3(-0.99f, 0.42f, 1.38f), new Vector3(0.99f, 0.42f, 1.38f),
            };
            foreach (var center in wheelCenters)
            {
                builder.AddCylinderAlongX(center, radius: 0.36f, halfWidth: 0.16f, segments: 10, subMesh: 1);
            }

            // Lamps are appearance-only geometry. No braking or turn semantics are inferred.
            builder.AddBox(new Vector3(-0.78f, 0.50f, 2.195f), new Vector3(-0.42f, 0.73f, 2.235f), 2);
            builder.AddBox(new Vector3(0.42f, 0.50f, 2.195f), new Vector3(0.78f, 0.73f, 2.235f), 2);
            builder.AddBox(new Vector3(-0.78f, 0.50f, -2.235f), new Vector3(-0.42f, 0.73f, -2.195f), 3);
            builder.AddBox(new Vector3(0.42f, 0.50f, -2.235f), new Vector3(0.78f, 0.73f, -2.195f), 3);

            var mesh = builder.ToMesh("XionganLowPolyCarMesh");
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }

        static Mesh SaveOrUpdateMesh(Mesh generated, string path)
        {
            var existing = AssetDatabase.LoadAssetAtPath<Mesh>(path);
            if (existing == null)
            {
                AssetDatabase.CreateAsset(generated, path);
                return generated;
            }

            EditorUtility.CopySerialized(generated, existing);
            Object.DestroyImmediate(generated);
            EditorUtility.SetDirty(existing);
            return existing;
        }

        static Material SaveOrUpdateMaterial(
            string path, string name, Color color, float metallic, float smoothness)
        {
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                var shader = Shader.Find("Standard");
                if (shader == null)
                {
                    throw new System.InvalidOperationException("Built-in Standard shader is unavailable");
                }
                material = new Material(shader);
                AssetDatabase.CreateAsset(material, path);
            }

            material.name = name;
            material.shader = Shader.Find("Standard");
            material.color = color;
            material.SetFloat("_Metallic", metallic);
            material.SetFloat("_Glossiness", smoothness);
            EditorUtility.SetDirty(material);
            return material;
        }

        static void EnsureFolder(string parent, string child)
        {
            var path = parent + "/" + child;
            if (!AssetDatabase.IsValidFolder(path))
            {
                AssetDatabase.CreateFolder(parent, child);
            }
        }

        sealed class MeshBuilder
        {
            readonly List<Vector3> vertices = new List<Vector3>();
            readonly List<int>[] triangles;

            public MeshBuilder(int subMeshCount)
            {
                triangles = new List<int>[subMeshCount];
                for (var i = 0; i < subMeshCount; i++) triangles[i] = new List<int>();
            }

            public void AddQuad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, int subMesh)
            {
                var start = vertices.Count;
                vertices.Add(a);
                vertices.Add(b);
                vertices.Add(c);
                vertices.Add(d);
                triangles[subMesh].Add(start);
                triangles[subMesh].Add(start + 1);
                triangles[subMesh].Add(start + 2);
                triangles[subMesh].Add(start);
                triangles[subMesh].Add(start + 2);
                triangles[subMesh].Add(start + 3);
            }

            public void AddTriangle(Vector3 a, Vector3 b, Vector3 c, int subMesh)
            {
                var start = vertices.Count;
                vertices.Add(a);
                vertices.Add(b);
                vertices.Add(c);
                triangles[subMesh].Add(start);
                triangles[subMesh].Add(start + 1);
                triangles[subMesh].Add(start + 2);
            }

            public void AddBox(Vector3 min, Vector3 max, int subMesh)
            {
                var p000 = new Vector3(min.x, min.y, min.z);
                var p001 = new Vector3(min.x, min.y, max.z);
                var p010 = new Vector3(min.x, max.y, min.z);
                var p011 = new Vector3(min.x, max.y, max.z);
                var p100 = new Vector3(max.x, min.y, min.z);
                var p101 = new Vector3(max.x, min.y, max.z);
                var p110 = new Vector3(max.x, max.y, min.z);
                var p111 = new Vector3(max.x, max.y, max.z);

                AddQuad(p001, p101, p111, p011, subMesh); // +Z
                AddQuad(p100, p000, p010, p110, subMesh); // -Z
                AddQuad(p101, p100, p110, p111, subMesh); // +X
                AddQuad(p000, p001, p011, p010, subMesh); // -X
                AddQuad(p010, p011, p111, p110, subMesh); // +Y
                AddQuad(p000, p100, p101, p001, subMesh); // -Y
            }

            public void AddWedgeCabin(
                float bottomRearZ, float bottomFrontZ, float topRearZ, float topFrontZ,
                float bottomY, float topY, float bottomHalfWidth, float topHalfWidth, int subMesh)
            {
                var blr = new Vector3(-bottomHalfWidth, bottomY, bottomRearZ);
                var brr = new Vector3(bottomHalfWidth, bottomY, bottomRearZ);
                var blf = new Vector3(-bottomHalfWidth, bottomY, bottomFrontZ);
                var brf = new Vector3(bottomHalfWidth, bottomY, bottomFrontZ);
                var tlr = new Vector3(-topHalfWidth, topY, topRearZ);
                var trr = new Vector3(topHalfWidth, topY, topRearZ);
                var tlf = new Vector3(-topHalfWidth, topY, topFrontZ);
                var trf = new Vector3(topHalfWidth, topY, topFrontZ);

                AddQuad(blf, brf, trf, tlf, subMesh);
                AddQuad(brr, blr, tlr, trr, subMesh);
                AddQuad(brf, brr, trr, trf, subMesh);
                AddQuad(blr, blf, tlf, tlr, subMesh);
                AddQuad(tlr, tlf, trf, trr, subMesh);
                AddQuad(blr, brr, brf, blf, subMesh);
            }

            public void AddCylinderAlongX(
                Vector3 center, float radius, float halfWidth, int segments, int subMesh)
            {
                var leftCenter = center + Vector3.left * halfWidth;
                var rightCenter = center + Vector3.right * halfWidth;
                for (var i = 0; i < segments; i++)
                {
                    var a0 = Mathf.PI * 2f * i / segments;
                    var a1 = Mathf.PI * 2f * (i + 1) / segments;
                    var yz0 = new Vector3(0f, Mathf.Cos(a0) * radius, Mathf.Sin(a0) * radius);
                    var yz1 = new Vector3(0f, Mathf.Cos(a1) * radius, Mathf.Sin(a1) * radius);
                    var l0 = leftCenter + yz0;
                    var l1 = leftCenter + yz1;
                    var r0 = rightCenter + yz0;
                    var r1 = rightCenter + yz1;
                    AddQuad(l0, r0, r1, l1, subMesh);
                    AddTriangle(leftCenter, l1, l0, subMesh);
                    AddTriangle(rightCenter, r0, r1, subMesh);
                }
            }

            public Mesh ToMesh(string name)
            {
                var mesh = new Mesh { name = name };
                mesh.indexFormat = vertices.Count > 65535 ? IndexFormat.UInt32 : IndexFormat.UInt16;
                mesh.SetVertices(vertices);
                mesh.subMeshCount = triangles.Length;
                for (var i = 0; i < triangles.Length; i++) mesh.SetTriangles(triangles[i], i);
                return mesh;
            }
        }
    }
}
