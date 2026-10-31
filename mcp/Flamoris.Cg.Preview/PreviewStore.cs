using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using Flamoris.Capture.Core;
using Flamoris.Capture.Imaging;

namespace Flamoris.Cg.Preview;

// Operator-owned output root, immutable generated clip directories, no remote paths.
public sealed partial class PreviewStore
{
    private readonly string root;
    public PreviewStore(string root)
    {
        this.root = Path.GetFullPath(root);
        DemandRegularPath(this.root);
        if (!Directory.Exists(this.root)) throw new CaptureFault("not_generated");
    }
    [GeneratedRegex("^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", RegexOptions.CultureInvariant)]
    private static partial Regex ClipIdPattern();
    public async Task<(ProcessedImage Image, JsonElement Provenance)> ReadAsync(string clipId,
        ScreenshotRequest options, CancellationToken token)
    {
        if (clipId is null || !ClipIdPattern().IsMatch(clipId)) throw new CaptureFault("invalid_request");
        string clip = Path.Combine(root, clipId);
        string manifestPath = Path.Combine(clip, "manifest.json");
        string previewPath = Path.Combine(clip, "preview.png");
        DemandRegularPath(clip); DemandRegularPath(manifestPath); DemandRegularPath(previewPath);
        await using var file = new FileStream(manifestPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (file.Length is < 1 or > 65536) throw new CaptureFault("resource_limit");
        // Bound even if a producer grows the file after the length check.
        byte[] buffer = new byte[65537]; int used = 0, n;
        while (used < buffer.Length && (n = await file.ReadAsync(buffer.AsMemory(used), token)) > 0) used += n;
        if (used > 65536) throw new CaptureFault("resource_limit");
        using var manifest = JsonDocument.Parse(buffer.AsMemory(0, used), new() { MaxDepth = 8, AllowDuplicateProperties = false });
        var m = manifest.RootElement;
        if (m.GetProperty("format").GetString() != "flamoris-cg-lab-result" || m.GetProperty("version").GetInt32() != 1
            || !m.GetProperty("artifacts").EnumerateArray().Any(x => x.GetString() == "preview.png")) throw new CaptureFault("invalid_manifest");
        var p = m.GetProperty("preview");
        int frame = p.GetProperty("frame").GetInt32();
        int duration = m.GetProperty("duration_frames").GetInt32();
        string sha = p.GetProperty("sha256").GetString() ?? "";
        if (sha.Length != 64 || !sha.All(char.IsAsciiHexDigit) || frame < 1 || frame > duration || duration > 240
            || p.GetProperty("camera").GetString() != "CG_Camera") throw new CaptureFault("invalid_manifest");
        if (!DateTimeOffset.TryParse(p.GetProperty("created_at_utc").GetString(), System.Globalization.CultureInfo.InvariantCulture,
            System.Globalization.DateTimeStyles.RoundtripKind, out var created)) throw new CaptureFault("invalid_manifest");
        string blender = m.GetProperty("blender").GetString() ?? "";
        string specHash = p.GetProperty("spec_sha256").GetString() ?? "";
        if (blender.Length is < 1 or > 64 || specHash.Length != 64 || !specHash.All(char.IsAsciiHexDigit)) throw new CaptureFault("invalid_manifest");
        await using var imageFile = new FileStream(previewPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        byte[] bytes = await ImageProcessor.ReadBoundedAsync(imageFile, token);
        if (p.GetProperty("byte_length").GetInt32() != bytes.Length
            || !string.Equals(sha, Convert.ToHexStringLower(SHA256.HashData(bytes)), StringComparison.OrdinalIgnoreCase))
            throw new CaptureFault("stale_preview");
        var image = ImageProcessor.Process(bytes, options, token);
        if (p.GetProperty("width").GetInt32() != image.Metadata.SourceWidth || p.GetProperty("height").GetInt32() != image.Metadata.SourceHeight)
            throw new CaptureFault("invalid_manifest");
        return (image, JsonSerializer.SerializeToElement(new { clipId, frame, camera = "CG_Camera", createdAtUtc = created,
            sourceSha256 = sha.ToLowerInvariant(), specSha256 = specHash.ToLowerInvariant(), blender, renderDevice = m.GetProperty("render_device").GetString() }));
    }
    private static void DemandRegularPath(string path)
    {
        for (var info = new FileInfo(path); info is not null; info = info.Directory is { } d ? new FileInfo(d.FullName) : null)
        {
            if ((File.GetAttributes(info.FullName) & FileAttributes.ReparsePoint) != 0) throw new CaptureFault("invalid_reference");
            if (info.Directory is null) break;
        }
    }
}
