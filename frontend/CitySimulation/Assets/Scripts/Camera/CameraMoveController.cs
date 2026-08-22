using UnityEngine;

/// <summary>
/// 简单的相机移动控制：WASD 平面移动，Q/E 上下移动。
/// 将此脚本挂到需要移动的 Camera 上即可。
/// </summary>
[RequireComponent(typeof(Camera))]
public class CameraMoveController : MonoBehaviour
{
    [Header("移动速度")]
    public float moveSpeed = 200f;
    [Header("按住 Shift 提速倍数")]
    public float sprintMultiplier = 2f;
    [Header("滚轮垂直移动倍数")]
    public float scrollMultiplier = 20000f;

    [Header("答辩演示镜头预设")]
    [Tooltip("启用数字键 1/2/3 的全景与路口特写镜头。")]
    public bool enablePresentationPresets = true;
    [Tooltip("数字键 1：30 路口全景。")]
    public Vector3 overviewPosition = new Vector3(400f, 900f, -180f);
    public Vector3 overviewTarget = new Vector3(400f, 0f, 500f);
    [Tooltip("数字键 1 的正交视野尺寸。")]
    public float overviewOrthographicSize = 560f;
    [Tooltip("数字键 2：北侧路口特写（J01 附近）。")]
    public Vector3 northJunctionPosition = new Vector3(600f, 155f, 755f);
    public Vector3 northJunctionTarget = new Vector3(600f, 0f, 960f);
    [Tooltip("数字键 3：路网中心路口特写（J19 附近）。")]
    public Vector3 centerJunctionPosition = new Vector3(300f, 155f, 270f);
    public Vector3 centerJunctionTarget = new Vector3(400f, 0f, 400f);
    [Tooltip("数字键 2/3 的正交视野尺寸，适合录制车辆与信号灯细节。")]
    public float junctionOrthographicSize = 95f;

    private void Update()
    {
        HandlePresentationPresetInput();

        float speed = moveSpeed * (Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift) ? sprintMultiplier : 1f);
        Vector3 dir = Vector3.zero;

        // 在水平面移动（忽略相机俯仰），适合俯视视角
        Vector3 flatForward = transform.forward; flatForward.y = 0f;
        Vector3 flatRight = transform.right;   flatRight.y = 0f;
        if (flatForward.sqrMagnitude < 0.0001f) flatForward = Vector3.forward; else flatForward.Normalize();
        if (flatRight.sqrMagnitude   < 0.0001f) flatRight   = Vector3.right;   else flatRight.Normalize();

        if (Input.GetKey(KeyCode.W)) dir += flatForward;
        if (Input.GetKey(KeyCode.S)) dir -= flatForward;
        if (Input.GetKey(KeyCode.A)) dir -= flatRight;
        if (Input.GetKey(KeyCode.D)) dir += flatRight;

        // 处理水平移动（不包含上下）
        Vector3 horizontalDir = dir;
        if (horizontalDir.sqrMagnitude > 0.001f)
        {
            horizontalDir.Normalize();
            transform.position += horizontalDir * speed * Time.deltaTime;
        }

        // 垂直移动：滚轮（独立敏感度） + Q/E 键（使用 moveSpeed）
        float scrollInput = Input.GetAxis("Mouse ScrollWheel");
        float verticalFromScroll = scrollInput * scrollMultiplier * Time.deltaTime;
        float verticalFromKeys = 0f;
        if (Input.GetKey(KeyCode.Q)) verticalFromKeys -= speed * Time.deltaTime;
        if (Input.GetKey(KeyCode.E)) verticalFromKeys += speed * Time.deltaTime;
        float verticalTotal = verticalFromScroll + verticalFromKeys;
        if (Mathf.Abs(verticalTotal) > 0.000001f)
        {
            transform.position += Vector3.up * verticalTotal;
        }
    }

    private void HandlePresentationPresetInput()
    {
        if (!enablePresentationPresets) return;

        if (Input.GetKeyDown(KeyCode.Alpha1))
        {
            ApplyPreset(overviewPosition, overviewTarget, overviewOrthographicSize);
        }
        else if (Input.GetKeyDown(KeyCode.Alpha2))
        {
            ApplyPreset(northJunctionPosition, northJunctionTarget, junctionOrthographicSize);
        }
        else if (Input.GetKeyDown(KeyCode.Alpha3))
        {
            ApplyPreset(centerJunctionPosition, centerJunctionTarget, junctionOrthographicSize);
        }
    }

    private void ApplyPreset(Vector3 position, Vector3 target, float orthographicSize)
    {
        transform.position = position;
        Vector3 lookDirection = target - position;
        if (lookDirection.sqrMagnitude > 0.0001f)
        {
            transform.rotation = Quaternion.LookRotation(lookDirection.normalized, Vector3.up);
        }

        // 本项目主相机使用正交投影；仅移动位置不会形成真正的“特写”。
        // 因此镜头预设同时调整视野尺寸，保证数字键 2/3 能直接用于答辩录制。
        var targetCamera = GetComponent<Camera>();
        if (targetCamera != null && targetCamera.orthographic && orthographicSize > 0f)
        {
            targetCamera.orthographicSize = orthographicSize;
        }
    }
}
