using System.Collections.Generic;
using System.Linq;

namespace CitySimulation.GameObjects.Validation
{
    public class ValidationResult
    {
        public List<string> errors = new();
        public bool IsValid => errors.Count == 0;

        public void AddError(string message)
        {
            if (!string.IsNullOrEmpty(message))
            {
                errors.Add(message);
            }
        }

        public void Merge(ValidationResult other)
        {
            if (other == null || other.IsValid)
            {
                return;
            }
            errors.AddRange(other.errors);
        }
    }
}
