namespace App.Services;

public enum Priority { Low, High }

public delegate void Handler(int code);

public record Job(string Name);
