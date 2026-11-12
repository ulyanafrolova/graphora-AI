namespace Worker;

public class Job : BackgroundService
{
    private readonly Queue queue = new();
    private readonly User owner;

    protected override Task ExecuteAsync(CancellationToken token) => Task.CompletedTask;
}
