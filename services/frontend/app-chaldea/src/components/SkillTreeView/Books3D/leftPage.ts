import * as THREE from 'three';
import type { PaperStock } from './bookTextures';
import { drawNodePageInk, type InkRegion } from './nodePageInk';
import type { NodePageModel } from './nodePageModel';
import { PAGE_H, createInkCanvas } from './spreadTextures';

/*
  The left-hand page of an open book, kept as layers: the paper, the book's
  introduction in ink, and a node's page in ink. Opening a node lets the
  introduction fade from the paper while the node's page soaks in from the top
  down; closing it runs the other way.

  The layers are blended in the page's shader. Each is uploaded once, when its
  writing changes, and the animation only moves a few uniforms — composing them
  on a canvas every frame meant re-uploading a whole page texture per frame,
  and opening a node stuttered.
*/

/** How long each change of writing takes, seconds. */
const INTRO_FADE = 0.5;
const INK_SOAK = 0.9;
const INK_FADE = 0.4;
/** Height of the wet edge as the ink soaks down the page, as a share of the page. */
const SOAK_EDGE = 0.16;

const inkTexture = (canvas: HTMLCanvasElement) => {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
};

interface Layer {
  ink: ReturnType<typeof createInkCanvas>;
  texture: THREE.CanvasTexture;
}

const makeLayer = (): Layer => {
  const ink = createInkCanvas();
  return { ink, texture: inkTexture(ink.canvas) };
};

export class LeftPageWriter {
  readonly material: THREE.MeshStandardMaterial;
  /** Where each control of the open node's page is, in canvas pixels. */
  regions: InkRegion[] = [];

  private readonly paperTexture: THREE.CanvasTexture;
  private readonly introTexture: THREE.CanvasTexture;
  private node: Layer = makeLayer();
  private outgoing: Layer = makeLayer();
  private nodeKey: number | null = null;
  private readonly uniforms = {
    uIntro: { value: null as THREE.Texture | null },
    uNode: { value: null as THREE.Texture | null },
    uOut: { value: null as THREE.Texture | null },
    uIntroAlpha: { value: 1 },
    uSoak: { value: 0 },
    uOutAlpha: { value: 0 },
  };

  constructor(
    paper: HTMLCanvasElement,
    intro: HTMLCanvasElement,
    private readonly stock: PaperStock,
    private readonly classInk: string,
  ) {
    this.paperTexture = inkTexture(paper);
    this.introTexture = inkTexture(intro);
    this.uniforms.uIntro.value = this.introTexture;
    this.uniforms.uNode.value = this.node.texture;
    this.uniforms.uOut.value = this.outgoing.texture;

    this.material = new THREE.MeshStandardMaterial({ map: this.paperTexture, roughness: 0.92 });
    const uniforms = this.uniforms;
    this.material.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, uniforms);
      shader.fragmentShader = shader.fragmentShader
        .replace(
          '#include <map_pars_fragment>',
          `#include <map_pars_fragment>
          uniform sampler2D uIntro;
          uniform sampler2D uNode;
          uniform sampler2D uOut;
          uniform float uIntroAlpha;
          uniform float uSoak;
          uniform float uOutAlpha;`,
        )
        .replace(
          '#include <map_fragment>',
          `#ifdef USE_MAP
            vec3 page = texture2D(map, vMapUv).rgb;
            vec4 intro = texture2D(uIntro, vMapUv);
            vec4 outInk = texture2D(uOut, vMapUv);
            vec4 nodeInk = texture2D(uNode, vMapUv);
            page = mix(page, intro.rgb, intro.a * uIntroAlpha);
            page = mix(page, outInk.rgb, outInk.a * uOutAlpha);
            // Soaking in from the head of the page (v = 1) toward its foot.
            float down = 1.0 - vMapUv.y;
            float front = uSoak * (1.0 + ${SOAK_EDGE.toFixed(2)});
            float wet = clamp((front - down) / ${SOAK_EDGE.toFixed(2)}, 0.0, 1.0);
            page = mix(page, nodeInk.rgb, nodeInk.a * wet);
            diffuseColor.rgb *= page;
          #endif`,
        );
    };
  }

  /** Writes (or rewrites) the open node's page; null closes it. */
  setNode(model: NodePageModel | null, hovered: string | null) {
    const key = model?.nodeId ?? null;
    if (key !== this.nodeKey) {
      // Whatever was written goes on fading from the paper while the new page soaks in.
      if (this.nodeKey !== null) {
        [this.outgoing, this.node] = [this.node, this.outgoing];
        this.uniforms.uOut.value = this.outgoing.texture;
        this.uniforms.uNode.value = this.node.texture;
        this.uniforms.uOutAlpha.value = this.uniforms.uSoak.value;
      }
      this.nodeKey = key;
      this.uniforms.uSoak.value = 0;
    }
    const { canvas, ctx } = this.node.ink;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    this.regions = model ? drawNodePageInk(ctx, PAGE_H, model, this.stock, this.classInk, hovered) : [];
    this.node.texture.needsUpdate = true;
  }

  /** Moves the ink on by a frame. */
  update(delta: number) {
    const u = this.uniforms;
    const showing = this.nodeKey !== null;
    const step = (value: number, target: number, seconds: number) =>
      value < target ? Math.min(target, value + delta / seconds) : Math.max(target, value - delta / seconds);
    u.uIntroAlpha.value = step(u.uIntroAlpha.value, showing ? 0 : 1, INTRO_FADE);
    if (showing) u.uSoak.value = step(u.uSoak.value, 1, INK_SOAK);
    u.uOutAlpha.value = step(u.uOutAlpha.value, 0, INK_FADE);
  }

  /** Whether the open node's page is written far enough down for its controls to be used. */
  get readable() {
    return this.nodeKey !== null && this.uniforms.uSoak.value > 0.6;
  }

  dispose() {
    this.material.dispose();
    this.paperTexture.dispose();
    this.introTexture.dispose();
    this.node.texture.dispose();
    this.outgoing.texture.dispose();
  }
}
