// One palette and type scale for the README images and this video: media/theme.json.
import theme from "../../media/theme.json";

export const C = theme.color;
export const SANS = theme.type.sans;
export const MONO = theme.type.mono;

// The README scale is tuned for an 830 px column; the video is 1920 px wide.
const K = 2.3;
export const T = {
  caption: Math.round(theme.type.scale.caption * K),
  body: Math.round(theme.type.scale.body * K),
  label: Math.round(theme.type.scale.label * K),
  title: Math.round(theme.type.scale.title * K),
  display: Math.round(theme.type.scale.display * K),
};
