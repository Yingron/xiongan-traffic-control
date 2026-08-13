#if UNITY_EDITOR
using System.IO;
using CitySimulation.Builder;
using CitySimulation.GameObjects;
using UnityEditor;
using UnityEngine;

namespace CitySimulation.EditorTools
{
    /// <summary>
    /// Menu items to build/reload the xiongan 30-intersection 6x5 road network from JSON.
    /// Located under the top-level menu 雄安路网.
    /// </summary>
    public static class RoadNetworkBuilderEditor
    {
        private const string MapId = "xiongan_30";

        [MenuItem("雄安路网/构建 xiongan_30 30路口 (使用现有GameServices)", priority = 10)]
        public static void BuildFromGameServices()
        {
            if (!Application.isPlaying)
            {
                EditorUtility.DisplayDialog(
                    "需要进入 Play 模式",
                    "GameServices.ObjectManager 需要在 Play 模式后初始化。\n\n请先点击 Play 进入 Play 模式，再重新执行此菜单。",
                    "确定");
                return;
            }
            var builder = new RoadNetworkBuilder();
            try
            {
                var report = builder.BuildFromJson(MapId);
                LogReport(report);
            }
            catch (FileNotFoundException fnf)
            {
                EditorUtility.DisplayDialog("找不到 JSON", fnf.Message, "确定");
            }
            catch (System.Exception ex)
            {
                Debug.LogException(ex);
                EditorUtility.DisplayDialog("构建失败", ex.Message, "确定");
            }
        }

        [MenuItem("雄安路网/构建 xiongan_30 (独立ObjectManager - 可在Edit模式预览)", priority = 20)]
        public static void BuildStandalone()
        {
            var builder = new RoadNetworkBuilder();
            try
            {
                // Standalone pipeline: instantiate a fresh PrefabFactory + ObjectManager and import.
                var factory = new PrefabFactory();
                var objectManager = new ObjectManager(factory);

                var path = RoadNetworkBuilder.ResolveJsonPath(MapId);
                if (string.IsNullOrEmpty(path))
                {
                    EditorUtility.DisplayDialog("找不到 JSON",
                        "请确认 xiongan_30.json 已放在 Assets/Scripts/Maps 目录。", "确定");
                    return;
                }
                var report = builder.BuildFromJsonFullPath(path, objectManager);
                LogReport(report);
            }
            catch (System.Exception ex)
            {
                Debug.LogException(ex);
                EditorUtility.DisplayDialog("构建失败", ex.Message, "确定");
            }
        }

        [MenuItem("雄安路网/打开 xiongan_30.json 所在目录", priority = 90)]
        public static void RevealJsonFolder()
        {
            var p = RoadNetworkBuilder.ResolveJsonPath(MapId);
            if (string.IsNullOrEmpty(p))
            {
                EditorUtility.DisplayDialog("未找到 JSON", "xiongan_30.json 不在 Assets/Scripts/Maps 中。", "确定");
                return;
            }
            EditorUtility.RevealInFinder(p);
        }

        [MenuItem("雄安路网/验证 xiongan_30.json 解析 (不生成对象)", priority = 30)]
        public static void ValidateJsonParse()
        {
            var path = RoadNetworkBuilder.ResolveJsonPath(MapId);
            if (string.IsNullOrEmpty(path))
            {
                Debug.LogError("[Validation] 找不到 xiongan_30.json");
                return;
            }
            var json = File.ReadAllText(path);
            int roads = CountOccurrences(json, "\"category\": 1") + CountOccurrences(json, "\"category\":1");
            int trafficLights = CountOccurrences(json, "\"category\": 4") + CountOccurrences(json, "\"category\":4");
            bool hasJ30 = json.Contains("\"J30\"");

            Debug.Log(
                $"[Validation] xiongan_30.json:\n" +
                $"  道路(Road, cat=1) 数  : {roads}\n" +
                $"  路口(TrafficLight, cat=4) : {trafficLights}\n" +
                $"  含J30路口            : {(hasJ30 ? "是" : "否")}\n" +
                $"  文件大小             : {new FileInfo(path).Length:N0} bytes\n" +
                $"  路径                 : {path}");
        }

        private static int CountOccurrences(string haystack, string needle)
        {
            if (string.IsNullOrEmpty(haystack) || string.IsNullOrEmpty(needle)) return 0;
            int count = 0, idx = 0;
            while ((idx = haystack.IndexOf(needle, idx, System.StringComparison.Ordinal)) != -1)
            {
                count++;
                idx += needle.Length;
            }
            return count;
        }

        private static void LogReport(BuildReport report)
        {
            var ok = report.IsValid ? "<color=green>[OK]</color>" : "<color=red>[ERR]</color>";
            Debug.Log(
                $"{ok} [RoadNetworkBuilder] 完成构建 mapId={report.mapId}\n" +
                $"  roads={report.roads}  trafficLights={report.trafficLights}/{report.intersectionsExpected}\n" +
                $"  bounds: {report.boundsMin:F1} ~ {report.boundsMax:F1}\n" +
                $"  warnings({report.warnings.Count}): {string.Join("; ", report.warnings)}\n" +
                $"  errors({report.errors.Count}): {string.Join("; ", report.errors)}");

            if (!report.IsValid)
            {
                EditorUtility.DisplayDialog(
                    "构建完成但有错误",
                    $"详见 Console 输出。\n路口数={report.trafficLights}/{report.intersectionsExpected}\n道路数={report.roads}",
                    "确定");
            }
            else if (report.warnings.Count > 0)
            {
                EditorUtility.DisplayDialog(
                    "构建完成（有警告）",
                    string.Join("\n", report.warnings),
                    "确定");
            }
            else
            {
                EditorUtility.DisplayDialog(
                    "构建成功",
                    $"xiongan_30 已加载：\n  道路 {report.roads} 条\n  路口 {report.trafficLights} 个\n范围 {report.boundsMin:F1} ~ {report.boundsMax:F1}",
                    "确定");
            }
        }
    }
}
#endif
