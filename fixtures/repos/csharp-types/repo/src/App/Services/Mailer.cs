namespace App.Services;

public class Mailer
{
    private readonly Clock clock = new Clock();

    public Envelope Wrap(string body) => new Envelope(body);
}
