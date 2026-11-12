namespace Web;

public class Endpoints
{
    private readonly Mailer mailer = new();
    private readonly Member member;
    private readonly HttpClient client;
    private readonly Type extensions = typeof(StringExtensions);

    public Task<Envelope> Send() => null;
}
