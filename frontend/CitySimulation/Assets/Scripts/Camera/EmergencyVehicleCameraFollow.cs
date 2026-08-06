using UnityEngine;

namespace CitySimulation.CameraControls
{
    [RequireComponent(typeof(Camera))]
    public sealed class EmergencyVehicleCameraFollow : MonoBehaviour
    {
        [Header("Follow")]
        [SerializeField] private Vector3 followOffset = new Vector3(0f, 18f, -28f);
        [SerializeField] private float positionSmoothTime = 0.18f;
        [SerializeField] private float rotationLerpSpeed = 8f;

        [Header("Look At")]
        [SerializeField] private Vector3 lookAtOffset = new Vector3(0f, 2.5f, 0f);

        private Transform _target;
        private Vector3 _velocity;
        private CameraMoveController _moveController;

        public bool IsFollowing => _target != null;

        private void Awake()
        {
            _moveController = GetComponent<CameraMoveController>();
        }

        private void LateUpdate()
        {
            if (_target == null)
            {
                return;
            }

            Vector3 targetPosition = _target.position + _target.TransformDirection(followOffset);
            transform.position = Vector3.SmoothDamp(
                transform.position,
                targetPosition,
                ref _velocity,
                Mathf.Max(0.01f, positionSmoothTime));

            Vector3 lookAt = _target.position + lookAtOffset;
            Vector3 lookDirection = lookAt - transform.position;
            if (lookDirection.sqrMagnitude > 0.001f)
            {
                Quaternion targetRotation = Quaternion.LookRotation(lookDirection.normalized, Vector3.up);
                transform.rotation = Quaternion.Slerp(
                    transform.rotation,
                    targetRotation,
                    Mathf.Max(0.01f, rotationLerpSpeed) * Time.deltaTime);
            }
        }

        public void Follow(Transform target)
        {
            if (target == null)
            {
                StopFollowing();
                return;
            }

            _target = target;
            _velocity = Vector3.zero;

            if (_moveController != null)
            {
                _moveController.enabled = false;
            }
        }

        public void StopFollowing()
        {
            _target = null;
            _velocity = Vector3.zero;

            if (_moveController != null)
            {
                _moveController.enabled = true;
            }
        }
    }
}
