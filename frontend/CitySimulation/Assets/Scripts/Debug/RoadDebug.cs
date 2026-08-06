using UnityEngine;
public class RoadDebug : MonoBehaviour
{
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.F12))
        {
            var lrs = FindObjectsOfType<LineRenderer>();
            Debug.Log($"Found {lrs.Length} LineRenderers:");
            foreach (var lr in lrs)
            {
                Debug.Log($"GO={lr.gameObject.name} GOid={lr.gameObject.GetInstanceID()} LRid={lr.GetInstanceID()} sharedMatId={(lr.sharedMaterial?lr.sharedMaterial.GetInstanceID().ToString():"null")}");
            }
        }
    }
}