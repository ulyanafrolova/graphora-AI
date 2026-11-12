namespace App.Models
{
    using Services;

    public partial class User
    {
        public bool IsValid() => Name.Length > 0;
    }
}
