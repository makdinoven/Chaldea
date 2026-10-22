import * as THREE from 'three';
import type { PaperStock } from './bookTextures';
import { drawPerks, drawSkillCard, type SkillRegion } from './skillPageInk';
import type { SkillPageModel } from './skillPageModel';
import { PAGE_H, PAGE_W, createInkCanvas } from './spreadTextures';

/*
  The two pages of a skill's spread, each its paper with the ink written over
  it, kept as textures the book can show — and the turning leaf can carry —
  and redrawn only when what they say, or the control under the pointer,
  changes.
*/

const pageTexture = (canvas: HTMLCanvasElement) => {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
};

export class SkillSpread {
  readonly left = createInkCanvas();
  readonly right = createInkCanvas();
  readonly leftTexture = pageTexture(this.left.canvas);
  readonly rightTexture = pageTexture(this.right.canvas);
  leftRegions: SkillRegion[] = [];
  rightRegions: SkillRegion[] = [];

  constructor(
    private readonly leftPaper: HTMLCanvasElement,
    private readonly rightPaper: HTMLCanvasElement,
    private readonly stock: PaperStock,
    private readonly classInk: string,
  ) {}

  write(model: SkillPageModel, hovered: string | null) {
    const { left, right, stock, classInk } = this;
    left.ctx.drawImage(this.leftPaper, 0, 0);
    this.leftRegions = drawSkillCard(left.ctx, PAGE_W, PAGE_H, model, stock, classInk, hovered);
    right.ctx.drawImage(this.rightPaper, 0, 0);
    this.rightRegions = drawPerks(right.ctx, PAGE_W, PAGE_H, model, stock, classInk, hovered);
    this.leftTexture.needsUpdate = true;
    this.rightTexture.needsUpdate = true;
  }

  dispose() {
    this.leftTexture.dispose();
    this.rightTexture.dispose();
  }
}
