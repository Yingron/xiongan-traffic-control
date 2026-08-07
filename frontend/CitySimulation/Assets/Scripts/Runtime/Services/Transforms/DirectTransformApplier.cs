using UnityEngine;

namespace CitySimulation.Runtime.Services.Transforms
{
    public sealed class DirectTransformApplier : ITransformApplier
    {
        public void Apply(GameObject gameObject, Vector3 position, Quaternion rotation)
        {
            if (gameObject == null)
            {
                return;
            }

            gameObject.transform.SetPositionAndRotation(position, rotation);
        }
    }
}
