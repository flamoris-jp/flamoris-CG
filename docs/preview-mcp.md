# Saved CG preview -> MCP image

CG owns immutable clip output and provenance. Capture owns image decoding,
ROI, scaling and encoding. Published `Flamoris.Mcp.Core` 1.4.0 owns MCP image
transport, grants, cancellation and disclosure revalidation. The CG adapter is
.NET 10 and references Capture.Imaging directly; Python does not reimplement
image processing and does not need to load a .NET DLL.

The builder creates `scene.blend`, `preview.png` and `manifest.json` in a **new**
output directory. Preview metadata includes dimensions, byte count, source image
and canonical validated-spec SHA-256, render frame, camera and UTC time.
Old manifests without preview provenance are not trusted: regenerate into a new
folder instead of silently guessing frame/camera information.

## Build and use

Check out this repository beside `flamoris-capture`, at the exact Capture commit
recorded in `config/preview-dependencies.json`. Both are Apache-2.0. On a different
layout set the absolute MSBuild property `CaptureSourceRoot` explicitly.

```sh
dotnet test mcp/Flamoris.Cg.Preview.Tests -c Release
dotnet publish mcp/Flamoris.Cg.Preview -c Release -r linux-x64 --self-contained true -o artifacts/preview
```

For a complete bundle with the image CLI, builder source, helper, licenses and
SHA-256 file receipt, run `python tools/publish_preview.py --capture-root
/absolute/flamoris-capture --output /new/bundle --rid linux-x64`. It verifies the
pinned Capture Git revision and refuses an existing output. Use reviewed, clean
source checkouts; this executes normal trusted .NET builds, not remote user code.

Use `win-x64` for Windows. The published directory includes the .NET runtime and
Skia native dependencies; retain `licenses/` and the runtime/package notices.
.NET SDK 10 is a build dependency, not a target-host installation requirement.
Ordinary Python scene validation still has no .NET or MCP dependency.

Configure a trusted local MCP client to execute:

```text
<absolute published executable> --root <absolute CG output root>
```

No network listener, new service or credential is required for this per-call
stdio adapter. The same-user Core pipe uses a random name and transient grant,
passed in memory to Core's stdio bridge. Only read-only access is enabled.
On locked-down Linux service accounts set `XDG_RUNTIME_DIR` to a private writable
user-owned directory (mode 0700); recent .NET 10 mutexes otherwise need the user's
home. This does not require weakening systemd protection or changing HOME.
The local parent controlling stdin/stdout is the authority to choose the root.
Do not expose an operator's arbitrary filesystem or use an untrusted shared root.

Tool: `preview.get`, arguments:

```json
{"input":{"clipId":"hello-preview","format":"png","maxEdge":1280}}
```

`clipId` is one path component matching `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.
Optional `roi` uses source-image pixels; `requireExactSize` prevents fallback
shrinking. No path or render code is accepted. The adapter never starts Blender,
GPU, Python scripts or network work from a tool query. The root and every path
component are checked for symlinks/reparse points. A manifest can only authorize
the fixed artifact `preview.png`; its bytes/dimensions/hash must agree. A trusted
local producer owns the directory, so concurrent malicious filesystem writers
are outside this API's trust boundary. Publish completed directories immutably.

The result is standard MCP `content`: a metadata text block plus **one actual
PNG/JPEG image block**. `structuredContent` contains image metadata and provenance,
without image data or filesystem paths. The binary payload is <=1 MiB; original
encoded input is <=32 MiB and source pixels obey Capture's policy. Metadata
includes output SHA-256 and source SHA-256, which need not be equal after
re-encoding. PNG preserves alpha/sRGB; JPEG explicitly uses a white matte.

Examples of safe errors: `invalid_request`, `invalid_reference`,
`not_generated`, `invalid_manifest`, `stale_preview`, `resource_limit`,
`response_too_large`, `forbidden`, `cancelled`. Errors never include an image.
Core revokes disclosure on shutdown and enforces guards/deadlines and envelope
limits. Queries cannot acquire screen capture consent or bypass another app.

## Existing Blender MCP path

`tools/preview_client.py` is a local diagnostic/bridge helper using the official
Python MCP client (`mcp>=1.28,<2`). It initializes the published stdio host,
discovers the tool and calls it once, preserving the resulting MCP content array:

```sh
python tools/preview_client.py --executable /absolute/preview/Flamoris.Cg.Preview --root /absolute/outputs --clip-id hello-preview
```

A trusted Blender-MCP caller can run this helper and forward its returned image
block to the chat UI. The helper's JSON is an envelope for transporting the
**already-created MCP response**, not a replacement public base64-returning API.
Use the direct stdio server when configuring an MCP client. The helper strips
ambient API/tunnel credentials from the child environment, uses the official
SDK and bounds the call. A separate Hub catalog/tunnel can be added later; no
live Hub registration or static catalog mutation is implicit in installation.

## Ownership and reuse decision

Cinema's paused orchestration is not involved. Its historical Blender bridge
owns a different scene/take contract and was not copied. CG's existing builder
already owns this lab manifest, so the change is a small provenance addition.
Capture.Imaging is a normal project dependency pinned to reviewed source for
now; do not copy its algorithms. Publishing it as a standalone NuGet package can
be considered when distribution demand justifies it. The portable CLI in the
Capture repository remains available to other Python callers.

See [first acceptance](preview-acceptance.md). CI covers Windows/Linux synthetic
images and the Core boundary; a real Blender/visual test is separate.
