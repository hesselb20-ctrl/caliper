import React from "react";
import { AbsoluteFill, Easing, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import example from "./example.json";
import { C, MONO, SANS, T } from "./theme";

export const FPS = 30;

// Scene lengths in frames. Total: 75 seconds.
const SCENES = { broken: 210, photos: 390, scale: 240, tree: 420, model: 300, edit: 300, print: 210, install: 180 } as const;
export const TOTAL_FRAMES = Object.values(SCENES).reduce((a, b) => a + b, 0);

const REPO = "github.com/hesselb20-ctrl/caliper";
const COMMAND = 'caliper scan photos/ --ref "hole spacing 40mm" --out part/';

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(0.2, 0.7, 0.2, 1);
const pad = (n: number, width = 3) => String(n).padStart(width, "0");
const frameImg = (name: string) => staticFile(`frames/${name}`);
const fmt = (v: number) => String(Math.round(v * 100) / 100);

/** 0 -> 1 over `length` frames starting at `start`, eased. */
const rise = (frame: number, start: number, length = 18) => interpolate(frame, [start, start + length], [0, 1], { ...clamp, easing: ease });

const appear = (frame: number, start: number, distance = 24): React.CSSProperties => {
  const t = rise(frame, start);
  return { opacity: t, transform: `translateY(${(1 - t) * distance}px)` };
};

const Background: React.FC = () => (
  <AbsoluteFill
    style={{
      backgroundColor: C.bg,
      backgroundImage: `linear-gradient(${C.panel} 1px, transparent 1px), linear-gradient(90deg, ${C.panel} 1px, transparent 1px)`,
      backgroundSize: "48px 48px",
    }}
  />
);

const Scene: React.FC<{ length: number; children: React.ReactNode }> = ({ length, children }) => {
  const frame = useCurrentFrame();
  const opacity = Math.min(rise(frame, 0, 12), interpolate(frame, [length - 12, length], [1, 0], clamp));
  return <AbsoluteFill style={{ opacity, fontFamily: SANS, color: C.text }}>{children}</AbsoluteFill>;
};

const Kicker: React.FC<{ children: React.ReactNode; at?: number }> = ({ children, at = 4 }) => {
  const frame = useCurrentFrame();
  return (
    <div style={{ fontFamily: MONO, fontSize: T.caption, letterSpacing: 3, color: C.accent, textTransform: "uppercase", ...appear(frame, at, 12) }}>
      {children}
    </div>
  );
};

const Headline: React.FC<{ children: React.ReactNode; at?: number; size?: number }> = ({ children, at = 10, size = T.title }) => {
  const frame = useCurrentFrame();
  return <div style={{ fontSize: size, fontWeight: 600, lineHeight: 1.12, marginTop: 18, ...appear(frame, at) }}>{children}</div>;
};

const Sub: React.FC<{ children: React.ReactNode; at?: number }> = ({ children, at = 24 }) => {
  const frame = useCurrentFrame();
  return <div style={{ fontSize: T.body, color: C.muted, marginTop: 20, lineHeight: 1.4, ...appear(frame, at) }}>{children}</div>;
};

const Panel: React.FC<{ style?: React.CSSProperties; children: React.ReactNode }> = ({ style, children }) => (
  <div style={{ backgroundColor: C.panel, border: `2px solid ${C.line}`, borderRadius: 18, ...style }}>{children}</div>
);

/** A terminal line that types itself. */
const Terminal: React.FC<{ text: string; at: number; speed?: number; style?: React.CSSProperties }> = ({ text, at, speed = 1.4, style }) => {
  const frame = useCurrentFrame();
  const shown = Math.max(0, Math.min(text.length, Math.floor((frame - at) * speed)));
  const cursor = frame >= at && Math.floor(frame / 15) % 2 === 0;
  return (
    <Panel style={{ padding: "22px 30px", fontFamily: MONO, fontSize: T.body, whiteSpace: "pre", ...appear(frame, at - 14, 16), ...style }}>
      <span style={{ color: C.muted }}>$ </span>
      {text.slice(0, shown)}
      <span style={{ color: C.accent, opacity: cursor ? 1 : 0 }}>▌</span>
    </Panel>
  );
};

const Part: React.FC<{ src: string; size: number; style?: React.CSSProperties }> = ({ src, size, style }) => (
  <Img src={src} style={{ width: size, height: size, ...style }} />
);

// ---- 1. the broken part -------------------------------------------------------------------------

const Broken: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const drop = spring({ frame: frame - 6, fps, config: { damping: 11, stiffness: 120 } });
  return (
    <Scene length={SCENES.broken}>
      <div style={{ position: "absolute", left: 150, top: 330, width: 800 }}>
        <Kicker>The problem</Kicker>
        <Headline size={T.display}>It snapped.</Headline>
        <Sub at={50}>The bracket is fifteen years old. Nobody sells a replacement, and there is no drawing.</Sub>
      </div>
      <Part
        src={frameImg("broken.png")}
        size={860}
        style={{ position: "absolute", left: 960, top: 110, opacity: Math.min(1, drop * 1.5), transform: `translateY(${(1 - drop) * -60}px) scale(${1 + frame * 0.00025})` }}
      />
    </Scene>
  );
};

// ---- 2. photos + reference ------------------------------------------------------------------------

const PHOTOS = ["top", "side", "front"] as const;
const ZOOM = 1.5; // the part sits small in the frame, so show the middle of each photo
const zoomed = (n: number) => 0.5 + (n - 0.5) * ZOOM;

const Photo: React.FC<{ name: string; width: number; height: number }> = ({ name, width, height }) => (
  <Img
    src={frameImg(`photo_${name}.jpg`)}
    style={{ position: "absolute", width: width * ZOOM, height: height * ZOOM, left: (-(ZOOM - 1) * width) / 2, top: (-(ZOOM - 1) * height) / 2, maxWidth: "none" }}
  />
);

const RefLine: React.FC<{ width: number; height: number; at: number }> = ({ width, height, at }) => {
  const frame = useCurrentFrame();
  const [[x1, y1], [x2, y2]] = (example.refLine as number[][]).map((point) => point.map(zoomed));
  const t = rise(frame, at, 24);
  const ax = x1 * width;
  const ay = y1 * height;
  const bx = ax + (x2 * width - ax) * t;
  const by = ay + (y2 * height - ay) * t;
  const labelOpacity = rise(frame, at + 22, 10);
  return (
    <>
      <svg width={width} height={height} style={{ position: "absolute", left: 0, top: 0 }}>
        <line x1={ax} y1={ay} x2={bx} y2={by} stroke={C.bg} strokeWidth={10} strokeLinecap="round" opacity={t > 0 ? 1 : 0} />
        <line x1={ax} y1={ay} x2={bx} y2={by} stroke={C.text} strokeWidth={4} strokeLinecap="round" opacity={t > 0 ? 1 : 0} />
        <circle cx={ax} cy={ay} r={8} fill={C.accent} opacity={t > 0 ? 1 : 0} />
        <circle cx={bx} cy={by} r={8} fill={C.accent} opacity={t > 0.98 ? 1 : 0} />
      </svg>
      <div
        style={{
          position: "absolute",
          left: ((x1 + x2) / 2) * width,
          top: ((y1 + y2) / 2) * height + 22,
          transform: "translateX(-50%)",
          opacity: labelOpacity,
          backgroundColor: C.bg,
          border: `2px solid ${C.accent}`,
          borderRadius: 10,
          padding: "4px 14px",
          fontFamily: MONO,
          fontSize: T.caption,
          whiteSpace: "nowrap",
        }}
      >
        40 mm
      </div>
    </>
  );
};

const PhotoCard: React.FC<{ name: string; width: number; at: number; refAt?: number }> = ({ name, width, at, refAt }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const height = width * 0.75;
  const pop = spring({ frame: frame - at, fps, config: { damping: 14 } });
  return (
    <div style={{ width, opacity: Math.min(1, pop * 1.4), transform: `translateY(${(1 - pop) * 50}px)` }}>
      <div style={{ position: "relative", width, height, borderRadius: 14, overflow: "hidden", border: `2px solid ${C.line}` }}>
        <Photo name={name} width={width} height={height} />
        {refAt !== undefined ? <RefLine width={width} height={height} at={refAt} /> : null}
      </div>
      <div style={{ fontFamily: MONO, fontSize: T.caption, color: C.muted, marginTop: 14 }}>{name}.jpg</div>
    </div>
  );
};

const Photos: React.FC = () => {
  const frame = useCurrentFrame();
  const second = frame >= 150;
  return (
    <Scene length={SCENES.photos}>
      <div style={{ position: "absolute", left: 150, top: 96 }}>
        <Kicker>Step 1</Kicker>
        <div style={{ position: "relative", height: 90 }}>
          <div style={{ position: "absolute", whiteSpace: "nowrap", opacity: second ? 1 - rise(frame, 150, 10) : 1 }}>
            <Headline>Take a few photos, square on.</Headline>
          </div>
          <div style={{ position: "absolute", whiteSpace: "nowrap" }}>
            <Headline at={158}>
              Add <span style={{ color: C.accent }}>one measurement</span> you know.
            </Headline>
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 150, top: 300, display: "flex", gap: 45 }}>
        {PHOTOS.map((name, i) => (
          <PhotoCard key={name} name={name} width={510} at={24 + i * 16} refAt={name === "top" ? 172 : undefined} />
        ))}
      </div>
      <Terminal text={COMMAND} at={236} style={{ position: "absolute", left: 150, top: 860 }} />
    </Scene>
  );
};

// ---- 3. scale -------------------------------------------------------------------------------------

const SCALE_ROWS = [
  { view: "top", note: "from the 40 mm reference" },
  { view: "side", note: "chained through the plate width" },
  { view: "front", note: "chained through the plate length" },
] as const;

const Scale: React.FC = () => {
  const frame = useCurrentFrame();
  const scales = example.scales as Record<string, { mm_per_px: number }>;
  return (
    <Scene length={SCENES.scale}>
      <div style={{ position: "absolute", left: 150, top: 200, ...appear(frame, 6) }}>
        <div style={{ position: "relative", width: 760, height: 570, borderRadius: 14, overflow: "hidden", border: `2px solid ${C.line}` }}>
          <Photo name="top" width={760} height={570} />
          <RefLine width={760} height={570} at={20} />
        </div>
      </div>
      <div style={{ position: "absolute", left: 1010, top: 200, width: 780 }}>
        <Kicker>Step 2</Kicker>
        <Headline>One measurement sets the scale.</Headline>
        <div style={{ marginTop: 50 }}>
          {SCALE_ROWS.map((row, i) => (
            <div key={row.view} style={{ display: "flex", alignItems: "baseline", gap: 24, padding: "20px 0", borderTop: `2px solid ${C.line}`, ...appear(frame, 60 + i * 34) }}>
              <div style={{ fontFamily: MONO, fontSize: T.body, width: 110 }}>{row.view}</div>
              <div style={{ fontFamily: MONO, fontSize: T.body, color: C.measure, width: 280 }}>{scales[row.view].mm_per_px.toFixed(4)} mm/px</div>
              <div style={{ fontSize: T.caption, color: C.muted }}>{row.note}</div>
            </div>
          ))}
        </div>
        <Sub at={170}>Only faces square to the camera are measured, so perspective cannot stretch them.</Sub>
      </div>
    </Scene>
  );
};

// ---- 4. the feature tree builds up -------------------------------------------------------------------

type Feature = { id: string; type: string; parent: string | null; params: Record<string, number | string> };
const FEATURES = example.features as unknown as Feature[];
const TREE_STEP = 40;
const TREE_START = 50;

const describeParams = (f: Feature) =>
  Object.entries(f.params)
    .filter(([key, value]) => !(key === "angle" && value === 0))
    .map(([key, value]) => `${key} ${typeof value === "number" ? fmt(value) : value}`)
    .join("   ");

const Tree: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene length={SCENES.tree}>
      <div style={{ position: "absolute", left: 150, top: 90 }}>
        <Kicker>Step 3</Kicker>
        <Headline>A feature tree, not a mesh.</Headline>
      </div>
      <Panel style={{ position: "absolute", left: 150, top: 270, width: 860, height: 748, padding: "20px 30px" }}>
        {FEATURES.map((f, i) => {
          const at = TREE_START + i * TREE_STEP;
          const depth = f.parent === null ? 0 : f.parent === "base" ? 1 : 2;
          const fresh = interpolate(frame, [at, at + 8, at + 34], [0, 1, 0], clamp);
          return (
            <div key={f.id} style={{ marginLeft: depth * 44, padding: "7px 14px", borderRadius: 10, backgroundColor: `rgba(255, 122, 26, ${fresh * 0.16})`, ...appear(frame, at, 14) }}>
              <span style={{ fontFamily: MONO, fontSize: T.body, fontWeight: 700 }}>{f.id}</span>
              <span style={{ fontFamily: MONO, fontSize: T.caption, color: C.accent, marginLeft: 18 }}>{f.type}</span>
              <div style={{ fontFamily: MONO, fontSize: T.caption - 3, color: C.muted, marginTop: 2, whiteSpace: "pre" }}>{describeParams(f)}</div>
            </div>
          );
        })}
      </Panel>
      <div style={{ position: "absolute", left: 1040, top: 190, width: 820, height: 820 }}>
        {FEATURES.map((f, i) => (
          <Part key={f.id} src={frameImg(`stage_${pad(i, 2)}.png`)} size={820} style={{ position: "absolute", opacity: rise(frame, TREE_START + i * TREE_STEP, 10) }} />
        ))}
      </div>
    </Scene>
  );
};

// ---- 5. the parametric model, rotating -----------------------------------------------------------------

const CodeLine: React.FC<{ line: string }> = ({ line }) => {
  const trimmed = line.length > 57 ? `${line.slice(0, 56)}…` : line;
  const parts = trimmed.split(/(P\["[^"]*"\])/g);
  const isComment = trimmed.trim().startsWith("#");
  return (
    <div style={{ whiteSpace: "pre", color: isComment ? C.muted : C.text, minHeight: 34 }}>
      {parts.map((part, i) => (part.startsWith('P["') ? <span key={i} style={{ color: C.accentSoft }}>{part}</span> : <span key={i}>{part}</span>))}
    </div>
  );
};

const Model: React.FC = () => {
  const frame = useCurrentFrame();
  const turn = Math.floor((frame / SCENES.model) * example.turnFrames) % example.turnFrames;
  const lines = (example.modelSource as string[]).filter((line, i, all) => !(line === "" && all[i - 1] === ""));
  return (
    <Scene length={SCENES.model}>
      <div style={{ position: "absolute", left: 150, top: 90 }}>
        <Kicker>Step 4</Kicker>
        <Headline>CadQuery you can read.</Headline>
      </div>
      <Panel style={{ position: "absolute", left: 150, top: 290, width: 930, height: 730, padding: "24px 30px", overflow: "hidden", fontFamily: MONO, fontSize: 25, ...appear(frame, 16) }}>
        <div style={{ color: C.muted, fontSize: T.caption - 4, marginBottom: 12 }}>part/model.py</div>
        {lines.slice(0, 18).map((line, i) => (
          <div key={i} style={{ opacity: rise(frame, 24 + i * 4, 8) }}>
            <CodeLine line={line} />
          </div>
        ))}
      </Panel>
      <Part src={frameImg(`turn_${pad(turn)}.png`)} size={800} style={{ position: "absolute", left: 1090, top: 200 }} />
    </Scene>
  );
};

// ---- 6. editing a parameter ----------------------------------------------------------------------------

const PARAM_KEYS = ["base.length", "base.width", "base.thickness", "fillet.radius", "flange.height", "flange.thickness", "h1.diameter", "slot1.length"];
const EDIT_AT = 70;
const REBUILD_AT = 124;
const MORPH_AT = 176;

const Edit: React.FC = () => {
  const frame = useCurrentFrame();
  const params = example.params as Record<string, number>;
  const newValue = String(example.editTo);
  const typed = Math.max(0, Math.min(newValue.length, Math.floor((frame - EDIT_AT - 12) / 6)));
  const editing = frame >= EDIT_AT;
  const step = Math.max(0, Math.min(example.editFrames - 1, Math.floor((frame - MORPH_AT) / 2)));
  const cursor = Math.floor(frame / 12) % 2 === 0;
  return (
    <Scene length={SCENES.edit}>
      <div style={{ position: "absolute", left: 150, top: 90 }}>
        <Kicker>Step 5</Kicker>
        <Headline>
          Change a number. <span style={{ color: C.accent }}>Get a new part.</span>
        </Headline>
      </div>
      <Panel style={{ position: "absolute", left: 150, top: 290, width: 800, padding: "26px 34px", fontFamily: MONO, fontSize: T.body - 2, ...appear(frame, 14) }}>
        <div style={{ color: C.muted, fontSize: T.caption - 4, marginBottom: 12 }}>part/params.json</div>
        {PARAM_KEYS.map((key) => {
          const target = key === "flange.height";
          const value = target && editing ? newValue.slice(0, typed) : fmt(params[key]);
          return (
            <div key={key} style={{ display: "flex", padding: "7px 14px", borderRadius: 8, backgroundColor: target && editing ? "rgba(255, 122, 26, 0.16)" : "transparent" }}>
              <span style={{ color: C.muted, width: 430 }}>"{key}":</span>
              <span style={{ color: target && editing ? C.accent : C.text }}>
                {value}
                {target && editing && frame < REBUILD_AT ? <span style={{ opacity: cursor ? 1 : 0 }}>▌</span> : null}
              </span>
            </div>
          );
        })}
      </Panel>
      <Terminal text="caliper rebuild part/" at={REBUILD_AT} style={{ position: "absolute", left: 150, top: 880 }} />
      <Part src={frameImg(`edit_${pad(step)}.png`)} size={840} style={{ position: "absolute", left: 990, top: 180 }} />
    </Scene>
  );
};

// ---- 7. the printable file -------------------------------------------------------------------------------

const FILES = [
  ["part.step", "editable solid for any CAD package"],
  ["part.stl", "mesh, ready for the slicer"],
  ["params.json", "every dimension, by name"],
  ["model.py", "the CadQuery source"],
  ["report.md", "scale, measurements, print check"],
] as const;

const Print: React.FC = () => {
  const frame = useCurrentFrame();
  const dfm = example.dfm as { walls: { name: string; thickness: number }[]; best_orientation: string; overhangs: { orientation: string; area_mm2: number }[]; min_wall_mm: number };
  const thinnest = [...dfm.walls].sort((a, b) => a.thickness - b.thickness)[0];
  const best = dfm.overhangs.find((o) => o.orientation === dfm.best_orientation) ?? dfm.overhangs[0];
  const checks = [
    `Thinnest wall ${thinnest.thickness.toFixed(1)} mm, minimum is ${dfm.min_wall_mm} mm`,
    `Print ${best.orientation.replace(" (as modelled)", "")}: ${Math.round(best.area_mm2)} mm² of overhang`,
    `Benchmark: mean error ${example.summary.mean_abs_error_mm.toFixed(2)} mm, worst ${example.summary.max_abs_error_mm.toFixed(2)} mm`,
  ];
  return (
    <Scene length={SCENES.print}>
      <div style={{ position: "absolute", left: 150, top: 90 }}>
        <Kicker>Step 6</Kicker>
        <Headline>Ready to print.</Headline>
      </div>
      <div style={{ position: "absolute", left: 150, top: 300, width: 820 }}>
        {FILES.map(([name, note], i) => (
          <div key={name} style={{ display: "flex", alignItems: "baseline", gap: 26, padding: "17px 0", borderTop: `2px solid ${C.line}`, ...appear(frame, 20 + i * 10) }}>
            <span style={{ fontFamily: MONO, fontSize: T.body, width: 300 }}>{name}</span>
            <span style={{ fontSize: T.caption, color: C.muted }}>{note}</span>
          </div>
        ))}
      </div>
      <div style={{ position: "absolute", left: 1040, top: 310, width: 790 }}>
        {checks.map((text, i) => (
          <div key={text} style={{ display: "flex", gap: 22, alignItems: "center", marginBottom: 34, ...appear(frame, 80 + i * 22) }}>
            <svg width={44} height={44} viewBox="0 0 44 44">
              <circle cx={22} cy={22} r={20} fill="none" stroke={C.ok} strokeWidth={3} />
              <path d="M13 23 L20 30 L32 16" fill="none" stroke={C.ok} strokeWidth={4} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span style={{ fontSize: T.body, lineHeight: 1.3 }}>{text}</span>
          </div>
        ))}
        <div style={{ fontSize: T.caption - 3, color: C.muted, marginTop: 10, ...appear(frame, 150) }}>
          Measured on a synthetic bracket: rendered photos of a known model, 14 dimensions, values before snapping.
        </div>
      </div>
    </Scene>
  );
};

// ---- 8. install --------------------------------------------------------------------------------------------

const Install: React.FC = () => {
  const frame = useCurrentFrame();
  const rule = rise(frame, 10, 26);
  return (
    <Scene length={SCENES.install}>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <div style={{ fontSize: 190, fontWeight: 700, letterSpacing: -4, lineHeight: 1, ...appear(frame, 4) }}>caliper</div>
        <div style={{ width: 640 * rule, height: 8, backgroundColor: C.accent, marginTop: 18, borderRadius: 4 }} />
        <div style={{ fontSize: T.label, color: C.muted, marginTop: 40, ...appear(frame, 24) }}>Photos and one known measurement in. Parametric CAD out.</div>
        <Terminal text={`pip install git+https://${REPO}.git`} at={50} speed={1.6} style={{ marginTop: 60 }} />
        <div style={{ fontFamily: MONO, fontSize: T.body, color: C.accent, marginTop: 40, ...appear(frame, 110) }}>{REPO}</div>
      </AbsoluteFill>
    </Scene>
  );
};

// ---- the whole film ---------------------------------------------------------------------------------------

const ORDER: [keyof typeof SCENES, React.FC][] = [
  ["broken", Broken],
  ["photos", Photos],
  ["scale", Scale],
  ["tree", Tree],
  ["model", Model],
  ["edit", Edit],
  ["print", Print],
  ["install", Install],
];

export const Tutorial: React.FC = () => {
  const frame = useCurrentFrame();
  let from = 0;
  return (
    <AbsoluteFill>
      <Background />
      {ORDER.map(([name, Component]) => {
        const start = from;
        from += SCENES[name];
        return (
          <Sequence key={name} from={start} durationInFrames={SCENES[name]}>
            <Component />
          </Sequence>
        );
      })}
      <div style={{ position: "absolute", left: 0, bottom: 0, height: 6, width: `${(frame / (TOTAL_FRAMES - 1)) * 100}%`, backgroundColor: C.accent }} />
    </AbsoluteFill>
  );
};
