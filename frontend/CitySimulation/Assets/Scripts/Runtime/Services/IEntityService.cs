namespace CitySimulation.Runtime.Services
{
    public interface IEntityService
    {
        void Initialize(CitySimulation.GameObjects.ObjectManager objectManager);
        void Tick(float dt);
    }
}
