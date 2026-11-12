using System;

namespace App.Services;

public class Clock
{
    public DateTime Now() => DateTime.UtcNow;
}
