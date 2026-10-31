using System.Text.Json;
using System.Text.Json.Serialization;
using Flamoris.Capture.Core;
using Flamoris.Mcp.Core;

namespace Flamoris.Cg.Preview;

public sealed class PreviewHost(PreviewStore store) : IMcpHost
{
    private readonly object lane = new();
    private readonly string runtime = Guid.NewGuid().ToString("N");
    private bool active = true;
    public HostSnapshot Snapshot => new("flamoris.cg", "0.2.0", runtime, runtime, 0, active) { HasDocument = false };
    public event Action? Invalidating;
    public Task<T> InvokeAsync<T>(Func<T> action, CancellationToken token)
    { lock (lane) { token.ThrowIfCancellationRequested(); return Task.FromResult(action()); } }
    public void Close() { lock (lane) { active = false; Invalidating?.Invoke(); } }
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) {
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow, PropertyNameCaseInsensitive = false, AllowDuplicateProperties = false };
    private sealed record Request([property: JsonRequired] string ClipId)
    {
        public string Format { get; init; } = "png";
        public int MaxEdge { get; init; } = 1280;
        public PixelRect? Roi { get; init; }
        public bool RequireExactSize { get; init; }
        public ScreenshotRequest Options() => new() { Format = Format, MaxEdge = MaxEdge, Roi = Roi, RequireExactSize = RequireExactSize };
    }
    public IEnumerable<HostTool> Tools()
    {
        yield return new HostImageTool<Request>("preview.get", "Read an immutable CG preview by managed clipId. Returns PNG/JPEG <= 1 MiB with frame and provenance. Never renders or accepts file paths.",
            JsonSerializer.SerializeToElement(new { type = "object", additionalProperties = false, required = new[] { "clipId" }, properties = new {
                clipId = new { type = "string", pattern = "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", maxLength = 64 },
                format = new { type = "string", @enum = new[] { "png", "jpeg" }, @default = "png" },
                maxEdge = new { type = "integer", minimum = 1, maximum = 1920, @default = 1280 },
                requireExactSize = new { type = "boolean", @default = false },
                roi = new { type = "object", additionalProperties = false, required = new[] { "x", "y", "width", "height" }, properties = new {
                    x = new { type = "integer", minimum = 0 }, y = new { type = "integer", minimum = 0 },
                    width = new { type = "integer", minimum = 1 }, height = new { type = "integer", minimum = 1 } } }
            } }),
            input => {
                var r = input.Deserialize<Request>(Json) ?? throw new JsonException();
                if (r.ClipId is null || r.Roi is null && input.TryGetProperty("roi", out _)) throw new JsonException();
                try { r.Options().Validate(); } catch (CaptureFault) { throw new JsonException(); }
                return r;
            }, async (context, request, token) => {
                try {
                    await context.BindDisclosureAsync(() => { if (!active) throw new McpFault(McpErrors.Forbidden); });
                    var (image, provenance) = await store.ReadAsync(request.ClipId, request.Options(), token);
                    return new McpResult(JsonSerializer.SerializeToElement(new { image = image.Metadata, provenance }, Json)) {
                        Image = new McpImage(image.Metadata.MimeType, image.Bytes) };
                }
                catch (CaptureFault e) { throw new McpFault(e.Code); }
                catch (FileNotFoundException) { throw new McpFault("not_generated"); }
                catch (DirectoryNotFoundException) { throw new McpFault("not_generated"); }
                catch (UnauthorizedAccessException) { throw new McpFault(McpErrors.Forbidden); }
                catch (Exception e) when (e is JsonException or KeyNotFoundException or InvalidOperationException or FormatException) { throw new McpFault("invalid_manifest"); }
                catch (IOException) { throw new McpFault("preview_unavailable"); }
            }) { RequiresDocument = false };
    }
}
