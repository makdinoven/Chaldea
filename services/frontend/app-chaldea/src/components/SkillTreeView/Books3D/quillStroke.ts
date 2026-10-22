import * as THREE from 'three';

/*
  A node written into the tree by the quill. The quill rises from its inkwell,
  crosses to the node, writes it, and goes back; the page shows the new state
  of the tree from under its nib outward, as wet ink spreading (RevealMaterial).
  Both run off the same clock, from the moment the node was taken.
*/

/** The quill's flight, seconds from the moment the node was taken. */
export const QUILL_TIMES = {
  /** Up out of the well and across, to hover over the node. */
  fly: 0.7,
  /** Down onto the page. */
  touch: 0.9,
  /** Writing the node. */
  write: 2.1,
  /** Back in the well. */
  home: 2.9,
} as const;

/** How the ink spreads: over the node while the quill writes it, then out across the page. */
const NODE_RADIUS_UV = 0.09;
const PAGE_RADIUS_UV = 1.6;
const SPREAD_SECONDS = 0.9;

/** Seconds on the clock both quill and page run on. */
export const inkClock = () => performance.now() / 1000;

/** How far the new ink has spread from the nib, in page UVs, `t` seconds after the node was taken. */
export const revealRadius = (t: number) => {
  if (t <= QUILL_TIMES.touch) return 0;
  if (t <= QUILL_TIMES.write) return NODE_RADIUS_UV * ((t - QUILL_TIMES.touch) / (QUILL_TIMES.write - QUILL_TIMES.touch));
  const k = Math.min(1, (t - QUILL_TIMES.write) / SPREAD_SECONDS);
  return NODE_RADIUS_UV + (PAGE_RADIUS_UV - NODE_RADIUS_UV) * k * k;
};
const REVEAL_DONE = QUILL_TIMES.write + SPREAD_SECONDS;

/** A node being written: where on the page, in world space and page UVs, and when it was taken. */
export interface QuillStroke {
  point: [number, number, number];
  at: number;
}

/**
 * A page material that can bring in a new picture of the page from a point
 * outward, the old one still showing beyond the edge of the spreading ink.
 * It owns the textures it is given: each is disposed once nothing shows it.
 */
export class RevealMaterial {
  readonly material: THREE.MeshStandardMaterial;
  private readonly uniforms = {
    uPrevMap: { value: null as THREE.Texture | null },
    uRevealCenter: { value: new THREE.Vector2() },
    uRevealRadius: { value: PAGE_RADIUS_UV },
  };
  private prev: THREE.Texture | null = null;
  private startedAt = 0;

  constructor(aspect: number) {
    this.material = new THREE.MeshStandardMaterial({ roughness: 0.92 });
    this.material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, this.uniforms);
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <common>',
          `#include <common>
uniform sampler2D uPrevMap;
uniform vec2 uRevealCenter;
uniform float uRevealRadius;`,
        )
        .replace(
          '#include <map_fragment>',
          `#ifdef USE_MAP
  vec4 sampledDiffuseColor = texture2D( map, vMapUv );
  vec2 fromNib = ( vMapUv - uRevealCenter ) * vec2( 1.0, ${aspect.toFixed(4)} );
  // A ragged wet edge rather than a clean circle.
  float rag = sin( atan( fromNib.y, fromNib.x ) * 9.0 + uRevealRadius * 40.0 ) * 0.012;
  float inked = 1.0 - smoothstep( uRevealRadius - 0.025, uRevealRadius, length( fromNib ) + rag );
  if ( uRevealRadius < ${PAGE_RADIUS_UV.toFixed(2)} ) {
    sampledDiffuseColor = mix( texture2D( uPrevMap, vMapUv ), sampledDiffuseColor, inked );
  }
  diffuseColor *= sampledDiffuseColor;
#endif`,
        );
    };
  }

  /**
   * Shows a new picture of the page: at once, or spreading from `center` (page
   * UVs) on the quill's clock from `at`.
   */
  show(texture: THREE.Texture, reveal?: { center: [number, number]; at: number }) {
    const current = this.material.map;
    // A redraw of the same page while the ink is still spreading (another
    // part of the progress arriving a moment later) leaves the spreading be.
    if (!reveal && this.prev) {
      if (current && current !== texture) current.dispose();
      this.material.map = texture;
      return;
    }
    this.finish();
    if (reveal && current && current !== texture) {
      this.prev = current;
      this.uniforms.uPrevMap.value = current;
      this.uniforms.uRevealCenter.value.set(reveal.center[0], reveal.center[1]);
      this.uniforms.uRevealRadius.value = 0;
      this.startedAt = reveal.at;
    } else if (current && current !== texture) {
      current.dispose();
    }
    this.material.map = texture;
    this.material.needsUpdate = true;
  }

  /** The new picture is still spreading over the old. */
  get revealing() {
    return this.prev !== null;
  }

  /** Moves the spreading ink on; call every frame. */
  update() {
    if (!this.prev) return;
    const t = inkClock() - this.startedAt;
    if (t >= REVEAL_DONE) this.finish();
    else this.uniforms.uRevealRadius.value = revealRadius(t);
  }

  /** Puts the whole new page in view at once. */
  private finish() {
    if (this.prev) {
      this.prev.dispose();
      this.prev = null;
    }
    this.uniforms.uPrevMap.value = null;
    this.uniforms.uRevealRadius.value = PAGE_RADIUS_UV;
  }

  dispose() {
    this.finish();
    this.material.map?.dispose();
    this.material.dispose();
  }
}

/**
 * Where the quill should be and how it should lie, `t` seconds into a stroke,
 * as a blend from its rest in the well toward the page: 0 at rest, 1 down on
 * the page. Also the nib's scribble across the node while it writes.
 */
export const quillPose = (t: number) => {
  const ease = (x: number) => x * x * (3 - 2 * x);
  if (t <= 0 || t >= QUILL_TIMES.home) return { reach: 0, hover: 0, arc: 0, scribble: new THREE.Vector3() };
  const scribble = new THREE.Vector3();
  if (t < QUILL_TIMES.fly) {
    const k = ease(t / QUILL_TIMES.fly);
    return { reach: k, hover: 1, scribble, arc: Math.sin(k * Math.PI) };
  }
  if (t < QUILL_TIMES.touch) {
    const k = ease((t - QUILL_TIMES.fly) / (QUILL_TIMES.touch - QUILL_TIMES.fly));
    return { reach: 1, hover: 1 - k, arc: 0, scribble };
  }
  if (t < QUILL_TIMES.write) {
    const w = t - QUILL_TIMES.touch;
    // Small looping strokes round the node, the nib lifting between them.
    scribble.set(Math.sin(w * 15) * 0.06, Math.max(0, Math.sin(w * 7.5)) * 0.03, Math.cos(w * 9) * 0.04 - 0.03 + w * 0.05);
    return { reach: 1, hover: 0, arc: 0, scribble };
  }
  const k = ease((t - QUILL_TIMES.write) / (QUILL_TIMES.home - QUILL_TIMES.write));
  return { reach: 1 - k, hover: k < 0.25 ? k * 4 : 1, scribble, arc: Math.sin(k * Math.PI) };
};
