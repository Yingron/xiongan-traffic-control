using UnityEngine;

namespace CitySimulation.Presentation
{
    [RequireComponent(typeof(Camera))]
    public sealed class ThirtyJunctionCameraController : MonoBehaviour
    {
        Vector3 _center;
        Vector3 _size;
        Camera _camera;
        bool _overview = true;

        public void Configure(Vector3 center, Vector3 size)
        {
            _center = center;
            _size = size;
            _camera = GetComponent<Camera>();
            SetOverview();
        }

        void Update()
        {
            if (Input.GetKeyDown(KeyCode.Home)) SetOverview();
            if (Input.GetKeyDown(KeyCode.C)) SetPresentation();
        }

        public void SetOverview()
        {
            if (_camera == null) _camera = GetComponent<Camera>();
            _overview = true;
            _camera.orthographic = false;
            _camera.fieldOfView = 52f;
            _camera.transform.position = _center + new Vector3(0f, Mathf.Max(900f, _size.magnitude * 0.78f), -_size.z * 0.52f);
            _camera.transform.LookAt(_center + Vector3.up * 4f);
        }

        public void SetPresentation()
        {
            if (_camera == null) _camera = GetComponent<Camera>();
            _overview = false;
            _camera.orthographic = false;
            _camera.fieldOfView = 56f;
            _camera.transform.position = _center + new Vector3(-92f, 84f, -118f);
            _camera.transform.LookAt(_center + Vector3.up * 3f);
        }
    }
}
