# Tutorial video

The 75 second caliper walkthrough, built in code with [Remotion](https://www.remotion.dev).

Everything on screen comes from the bracket example's real output:

- `public/frames/` holds pre-rendered frames: the three photos, the model growing feature by feature, a turntable of the generated STL, and the flange height swept from 40.5 to 60 mm by rebuilding the model at every step.
- `src/example.json` holds the feature tree, parameters, calibration and benchmark numbers the video quotes.

Both are written by `python scripts/make_media.py --frames` from the repository root (run `python examples/bracket/run_example.py` first).

## Render

```bash
npm install
npm run render
```

`npm run render` writes a JPEG frame sequence to `out/frames/` and then encodes `../media/tutorial.mp4` and `../media/preview.gif` with ffmpeg, which must be on your PATH.

```bash
npm run studio
```

opens the Remotion studio to scrub through the scenes in `src/Tutorial.tsx`.

On Windows, if the render fails with `spawn ... chrome-headless-shell.exe ENOENT`, the project path is too long. Move the repository to a shorter path, or copy `node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64` somewhere short and pass `--browser-executable=<that folder>/chrome-headless-shell.exe`.
