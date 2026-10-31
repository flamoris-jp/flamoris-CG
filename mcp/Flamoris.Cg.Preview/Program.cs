using Flamoris.Cg.Preview;
using Flamoris.Mcp.Core;
using Flamoris.Logging;

// stdout belongs exclusively to the official Core stdio transport.
using var stdout = Console.OpenStandardOutput();
Console.SetOut(Console.Error);
using var stop = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop.Cancel(); };
try
{
    if (args.Length != 2 || args[0] != "--root") { Console.Error.WriteLine("Usage: Flamoris.Cg.Preview --root <trusted immutable CG output root>"); return 2; }
    var host = new PreviewHost(new PreviewStore(args[1]));
    var options = new McpOptions { ApplicationLifetime = true, RequestTimeoutMs = 30000, MaxConcurrentRequests = 1 };
    using var boundary = new McpBoundary(host, host.Tools(), options, new McpDiagnostics(FlamorisLogger.Create()));
    var grant = await boundary.EnableAsync(McpPermission.ReadOnly, stop.Token);
    var endpoint = new LocalMcpEndpoint(boundary).RunAsync(grant, stop.Token);
    try {
        await StdioBridge.RunAsync(options.PipeName, grant.ExportCredential(), Console.OpenStandardInput(), stdout, cancellationToken: stop.Token);
    }
    finally { host.Close(); stop.Cancel(); await endpoint; }
    return 0;
}
catch (OperationCanceledException) { return 0; }
catch { Console.Error.WriteLine("CG preview connection ended."); return 1; }
