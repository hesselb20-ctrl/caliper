import { Composition } from "remotion";
import { FPS, TOTAL_FRAMES, Tutorial } from "./Tutorial";

export const Root = () => (
  <Composition id="Tutorial" component={Tutorial} durationInFrames={TOTAL_FRAMES} fps={FPS} width={1920} height={1080} />
);
