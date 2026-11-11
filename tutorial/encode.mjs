// Encode the rendered frame sequence to media/tutorial.mp4 and media/preview.gif with ffmpeg.
// Rendering stills and encoding separately keeps the colours exact (BT.709, limited range).
import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frames = join(here, "out", "frames");
const media = join(here, "..", "media");
const first = readdirSync(frames).filter((f) => f.endsWith(".jpeg")).sort()[0];
const digits = first.match(/(\d+)\.jpeg$/)[1].length;
const pattern = join(frames, first.replace(/\d+\.jpeg$/, `%0${digits}d.jpeg`));
const run = (args) => execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", ...args], { stdio: "inherit" });

run([
  "-framerate", "30", "-i", pattern,
  "-vf", "scale=in_range=pc:in_color_matrix=bt601:out_range=tv:out_color_matrix=bt709,format=yuv420p",
  "-c:v", "libx264", "-preset", "slow", "-crf", "18",
  "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
  "-movflags", "+faststart",
  join(media, "tutorial.mp4"),
]);

// The preview is a silent, double-speed cut small enough to sit in a README.
const palette = join(here, "out", "palette.png");
const filter = "setpts=PTS/2,fps=8,scale=720:-1:flags=lanczos";
run(["-framerate", "30", "-i", pattern, "-vf", `${filter},palettegen=max_colors=96:stats_mode=diff`, palette]);
run(["-framerate", "30", "-i", pattern, "-i", palette, "-lavfi", `${filter}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle`, join(media, "preview.gif")]);
console.log("wrote media/tutorial.mp4 and media/preview.gif");
