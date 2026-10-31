using System.Text.Json;
using System.Security.Cryptography;
using Flamoris.Cg.Preview;
using Flamoris.Capture.Core;
using Flamoris.Logging;
using Flamoris.Mcp.Core;
using SkiaSharp;
using Xunit;

public sealed class PreviewTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "cg-tests-" + Guid.NewGuid().ToString("N"));
    public PreviewTests() { Directory.CreateDirectory(root); Create("clip1", SKColors.Red); }
    private void Create(string id, SKColor color)
    {
        string dir = Path.Combine(root, id); Directory.CreateDirectory(dir);
        using var b = new SKBitmap(32, 16); b.Erase(color);
        using var data = b.Encode(SKEncodedImageFormat.Png, 100); var bytes = data.ToArray();
        File.WriteAllBytes(Path.Combine(dir, "preview.png"), bytes);
        File.WriteAllText(Path.Combine(dir, "manifest.json"), JsonSerializer.Serialize(new {
            format = "flamoris-cg-lab-result", version = 1, blender = "test", duration_frames = 24,
            render_device = "CPU", artifacts = new[] { "preview.png" }, preview = new {
                frame = 12, camera = "CG_Camera", width = 32, height = 16, byte_length = bytes.Length,
                sha256 = Convert.ToHexStringLower(SHA256.HashData(bytes)), spec_sha256 = new string('a', 64),
                created_at_utc = "2026-11-01T00:00:00+00:00" } }));
    }
    private McpBoundary Boundary(out PreviewHost host)
    {
        host = new(new(root)); return new(host, host.Tools(), new() { ApplicationLifetime = true }, new(FlamorisLogger.Create()));
    }
    [Fact] public async Task ActualImageAndSeparateImmutableClips()
    {
        Create("clip2", SKColors.Blue);
        using var b = Boundary(out _); using var g = await b.EnableAsync(McpPermission.ReadOnly);
        foreach (var (id, expected) in new[] { ("clip1", SKColors.Red), ("clip2", SKColors.Blue) }) {
            var result = await b.InvokeAsync(g, "preview.get", JsonSerializer.SerializeToElement(new { clipId = id }), null);
            Assert.False(result.IsError, result.Error); Assert.NotNull(result.Image);
            using var image = SKBitmap.Decode(result.Image.Bytes.ToArray()); Assert.Equal(expected, image.GetPixel(0,0));
            Assert.Equal(id, result.Value!.Value.GetProperty("provenance").GetProperty("clipId").GetString());
            Assert.DoesNotContain("base64", result.Value.Value.GetRawText());
        }
    }
    [Theory][InlineData("../clip1")][InlineData("/tmp/clip1")][InlineData("clip1/preview.png")][InlineData("")]
    public async Task RejectPaths(string id)
    {
        using var b = Boundary(out _); using var g = await b.EnableAsync(McpPermission.ReadOnly);
        var r = await b.InvokeAsync(g, "preview.get", JsonSerializer.SerializeToElement(new { clipId = id }), null);
        Assert.Equal("invalid_request", r.Error); Assert.Null(r.Image);
    }
    [Fact] public async Task MissingChangedMalformedAndRevokedNeverDisclose()
    {
        using var b = Boundary(out var h); using var g = await b.EnableAsync(McpPermission.ReadOnly);
        async Task<McpResult> Read(string id) => await b.InvokeAsync(g, "preview.get", JsonSerializer.SerializeToElement(new { clipId = id }), null);
        Assert.Equal("not_generated", (await Read("absent")).Error);
        File.WriteAllBytes(Path.Combine(root, "clip1", "preview.png"), [1,2,3]);
        Assert.Equal("stale_preview", (await Read("clip1")).Error);
        File.WriteAllText(Path.Combine(root, "clip1", "manifest.json"), "{}");
        Assert.Equal("invalid_manifest", (await Read("clip1")).Error);
        h.Close(); var revoked = await Read("clip1"); Assert.Equal("unauthorized", revoked.Error); Assert.Null(revoked.Image);
    }
    [Fact] public async Task SymlinkUnknownAndNullRejected()
    {
        using var b = Boundary(out _); using var g = await b.EnableAsync(McpPermission.ReadOnly);
        foreach (var json in new[] { "{\"clipId\":\"clip1\",\"path\":\"/etc/passwd\"}", "{\"clipId\":null}", "{\"clipId\":\"clip1\",\"roi\":null}", "{\"clipId\":\"clip1\",\"clipId\":\"clip1\"}" }) {
            var r = await b.InvokeAsync(g, "preview.get", JsonDocument.Parse(json).RootElement, null);
            Assert.Equal("invalid_request", r.Error); Assert.Null(r.Image);
        }
        // Windows developer-mode/admin symlink privileges are not required by ordinary CI.
        if (!OperatingSystem.IsWindows()) {
            Directory.CreateSymbolicLink(Path.Combine(root,"linked"), Path.Combine(root,"clip1"));
            var r = await b.InvokeAsync(g,"preview.get",JsonSerializer.SerializeToElement(new { clipId = "linked" }),null);
            Assert.Equal("invalid_reference", r.Error); Assert.Null(r.Image);
        }
    }
    [Fact] public async Task CancellationAndSmallEnvelope()
    {
        var h = new PreviewHost(new(root)); using var b = new McpBoundary(h,h.Tools(),new() { ApplicationLifetime=true, MaxRequestBytes=1024 },new(FlamorisLogger.Create()));
        using var g = await b.EnableAsync(McpPermission.ReadOnly);
        var r = await b.InvokeAsync(g,"preview.get",JsonSerializer.SerializeToElement(new { clipId="clip1" }),null);
        Assert.Equal("response_too_large",r.Error); Assert.Null(r.Image);
        using var c = new CancellationTokenSource(); c.Cancel();
        r = await b.InvokeAsync(g,"preview.get",JsonSerializer.SerializeToElement(new { clipId="clip1" }),null,c.Token);
        Assert.Equal("cancelled",r.Error); Assert.Null(r.Image);
    }
    public void Dispose() { Directory.Delete(root,true); }
}
