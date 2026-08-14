using System;
using System.Collections.Generic;
using System.IO;
using CitySimulation.DTO;
using CitySimulation.Global;
using UnityEngine;

namespace CitySimulation.GameObjects
{
    [Serializable]
    public class NewMapSettings
    {
        public string mapId = "xiongan_30";
    }

    [Serializable]
    internal class MapEntityListWrapper
    {
        public ObjectManager.MapSnapshot snapshot = new ObjectManager.MapSnapshot();
    }

    /// <summary>
    /// Handles map save/load: serialize all DTOs to JSON file and restore via ObjectManager.ImportAll.
    /// </summary>
    public class MapManager
    {
        private readonly ObjectManager _objectManager;
        private readonly string _mapsFolder;
        private string _currentMapId = "xiongan_30";

        public MapManager(ObjectManager objectManager = null)
        {
            _objectManager = objectManager ?? GameServices.ObjectManager;
            _mapsFolder = ResolveWorkspaceMapsFolder();
            Directory.CreateDirectory(_mapsFolder);
        }

        public void CreateNewMap(NewMapSettings settings)
        {
            _currentMapId = string.IsNullOrEmpty(settings?.mapId) ? "xiongan_30" : settings.mapId;
            // Clear runtime entities
            _objectManager.ImportAll(new ObjectManager.MapSnapshot());
        }

        public void SetCurrentMapId(string mapId)
        {
            _currentMapId = string.IsNullOrEmpty(mapId) ? "xiongan_30" : mapId;
        }

        public ObjectManager.MapSnapshot LoadMap()
        {
            var path = GetPath(_currentMapId);
            UnityEngine.Debug.Log($"[MapManager] LoadMap path: {path}");
            if (!File.Exists(path))
            {
                var empty = new ObjectManager.MapSnapshot();
                _objectManager.ImportAll(empty);
                return empty;
            }
            var json = File.ReadAllText(path);
            var wrapper = JsonUtility.FromJson<MapEntityListWrapper>(json) ?? new MapEntityListWrapper();
            var snap = wrapper.snapshot ?? new ObjectManager.MapSnapshot();
            _objectManager.ImportAll(snap);
            return snap;
        }

        public ObjectManager.MapSnapshot LoadMap(string mapId)
        {
            SetCurrentMapId(mapId);
            return LoadMap();
        }

        public bool SaveMap()
        {
            var saved = _objectManager.ExportAll();
            var path = GetPath(_currentMapId);
            UnityEngine.Debug.Log($"[MapManager] SaveMap path: {path}");
            Directory.CreateDirectory(_mapsFolder);
            var wrapper = new MapEntityListWrapper { snapshot = saved ?? new ObjectManager.MapSnapshot() };
            var json = JsonUtility.ToJson(wrapper, true);
            File.WriteAllText(path, json);
            return true;
        }

        /// <summary>
        /// Convenience: export from ObjectManager then save with current mapId.
        /// </summary>
        public bool SaveCurrentFromManager()
        {
            return SaveMap();
        }

        private string GetPath(string mapId)
        {
            var safeId = string.IsNullOrEmpty(mapId) ? "xiongan_30" : mapId;
            return Path.Combine(_mapsFolder, safeId + ".json");
        }

        private static string ResolveWorkspaceMapsFolder()
        {
            var primary = Path.Combine(Application.dataPath, "Scripts", "Maps");
            if (File.Exists(Path.Combine(primary, "xiongan_30.json")))
            {
                return primary;
            }

            // In a Windows player build, Application.dataPath points to
            // <build>/<name>_Data. During local experiments the editable maps
            // often still live in the Unity project under Assets/Scripts/Maps.
            var projectMaps = Path.GetFullPath(
                Path.Combine(Application.dataPath, "..", "..", "Assets", "Scripts", "Maps"));
            if (File.Exists(Path.Combine(projectMaps, "xiongan_30.json")))
            {
                return projectMaps;
            }

            return primary;
        }
    }
}
