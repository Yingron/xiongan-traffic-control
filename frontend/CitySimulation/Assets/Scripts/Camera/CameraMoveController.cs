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

    private void Update()
    {
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
}
