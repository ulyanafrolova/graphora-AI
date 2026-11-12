using Core.Domain;
using Core.Shared;
using Infra;
using Tools.Diagnostics;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Serilog;
using Serilog.Events;
using Tests.Core;

namespace Web.Controllers;

public class HomeController : Controller
{
    public void Index() { }
}
