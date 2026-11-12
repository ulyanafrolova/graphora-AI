using System.Collections.Generic;
using System.Threading.Tasks;
using App.Services;
using App.Extensions;
using App.Jobs;
using App.Checks;
using App.Timers;
using App.Legacy;
using Serilog;

namespace App.Web.Controllers;

[Audit]
[Traced]
public class HomeController
{
    private readonly Mailer mailer = new Mailer();
    private readonly List<App.Models.User> users = new();
    private readonly ILogger log;
    private Timer timer;

    public Task Run(Settings settings, Settings.Smtp smtp)
    {
        var name = "x".Shout();
        Mailer.Equals(mailer, null);
        return null;
    }
}
