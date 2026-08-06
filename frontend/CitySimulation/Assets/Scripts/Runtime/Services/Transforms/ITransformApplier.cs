using UnityEngine;

namespace CitySimulation.Runtime.Services.Transforms
{
    public interface ITransformApplier
    {
        void Apply(GameObject gameObject, Vector3 position, Quaternion rotation);
    }
}
