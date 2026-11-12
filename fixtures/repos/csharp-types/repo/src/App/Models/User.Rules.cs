namespace App.Models;

public partial class User
{
    public bool IsValid() => Name.Length > 0;
}
