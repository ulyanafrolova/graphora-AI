using Mail = App.Services.Mailer;
using Unused = App.Services.Queue;
using Zone = App.Settings.Smtp;

namespace App;

public class Aliases
{
    private Mail mail;
    private Zone zone;
}
