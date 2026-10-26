// Renders each scraped product once, offscreen, as a glossy container in the ShelfBrief style: the shape comes
// from its category, the tint from its brand, the label from its name. One WebGL context draws every product
// in turn, hands each frame back as a small image, then is thrown away, so no 3D keeps running on the page.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

const PORCELAIN = new THREE.Color("#F7EFEB");
const INK = "#3B1520";
const GOLD = new THREE.Color("#D8BC98");

const SHAPE_BY_CATEGORY = {
  "Serum & Face Oil": "dropper", "Eye & Lip Care": "jar", "Moisturiser": "jar", "Face Mask & Scrub": "jar",
  "Sunscreen": "tube", "Face Wash": "tube", "Hair Styling": "jar", "Shampoo & Conditioner": "pump",
  "Body Care": "pump", "Toner & Mist": "pump", "Hair Oil & Serum": "oil", "Beard & Shaving": "oil",
};

const lathe = (pts, seg = 56) => new THREE.LatheGeometry(pts.map(([x, y]) => new THREE.Vector2(x, y)), seg);

// Label band: the front ~100° of a cylinder, so the print faces the camera.
function band(r, y0, y1, mat) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, y1 - y0, 40, 1, true, -0.95, 1.9), mat);
  m.position.y = (y0 + y1) / 2;
  return m;
}

const SHAPES = {
  dropper(m) {
    const g = new THREE.Group();
    g.add(new THREE.Mesh(lathe([[0, 0], [0.29, 0], [0.32, 0.04], [0.32, 0.64], [0.27, 0.75], [0.12, 0.8], [0.12, 0.87], [0, 0.87]]), m.body));
    g.add(band(0.323, 0.14, 0.56, m.label));
    const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, 0.17, 32), m.cap); collar.position.y = 0.94; g.add(collar);
    g.add(new THREE.Mesh(lathe([[0, 1.02], [0.11, 1.03], [0.125, 1.15], [0.095, 1.28], [0, 1.31]]), m.bulb));
    return { g, h: 1.31, w: 0.66 };
  },
  pump(m) {
    const g = new THREE.Group();
    g.add(new THREE.Mesh(lathe([[0, 0], [0.29, 0], [0.31, 0.05], [0.31, 1.0], [0.24, 1.1], [0.1, 1.14], [0, 1.14]]), m.body));
    g.add(band(0.313, 0.24, 0.8, m.label));
    const collar = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.12, 32), m.cap); collar.position.y = 1.2; g.add(collar);
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.16, 16), m.cap); stem.position.y = 1.33; g.add(stem);
    const head = new THREE.Mesh(new RoundedBoxGeometry(0.36, 0.1, 0.13, 2, 0.03), m.cap); head.position.set(0.08, 1.44, 0); g.add(head);
    return { g, h: 1.49, w: 0.62 };
  },
  jar(m) {
    const g = new THREE.Group();
    g.add(new THREE.Mesh(lathe([[0, 0], [0.42, 0], [0.46, 0.05], [0.46, 0.38], [0.41, 0.42], [0, 0.42]]), m.body));
    g.add(band(0.463, 0.08, 0.34, m.label));
    g.add(new THREE.Mesh(lathe([[0, 0.42], [0.47, 0.42], [0.48, 0.45], [0.48, 0.6], [0.45, 0.62], [0, 0.62]]), m.cap));
    return { g, h: 0.62, w: 0.96 };
  },
  tube(m) {
    const g = new THREE.Group();
    const geo = new THREE.CylinderGeometry(0.24, 0.24, 1.1, 44, 14, true);
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const t = (p.getY(i) + 0.55) / 1.1;          // 0 at the cap end, 1 at the crimp
      p.setX(i, p.getX(i) * (1 + 0.32 * t));
      p.setZ(i, p.getZ(i) * (1 - 0.88 * t));
    }
    geo.computeVertexNormals();
    const body = new THREE.Mesh(geo, m.body); body.position.y = 0.78; g.add(body);
    const label = new THREE.Mesh(new THREE.PlaneGeometry(0.42, 0.5), m.label); label.position.set(0, 0.72, 0.205); label.rotation.x = -0.05; g.add(label);
    const crimp = new THREE.Mesh(new THREE.BoxGeometry(0.64, 0.06, 0.05), m.body); crimp.position.y = 1.34; g.add(crimp);
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.22, 0.22, 32), m.cap); cap.position.y = 0.11; g.add(cap);
    return { g, h: 1.37, w: 0.66 };
  },
  oil(m) {
    const g = new THREE.Group();
    g.add(new THREE.Mesh(lathe([[0, 0], [0.24, 0], [0.26, 0.04], [0.26, 0.92], [0.2, 1.02], [0.09, 1.07], [0.09, 1.13], [0, 1.13]]), m.body));
    g.add(band(0.263, 0.18, 0.78, m.label));
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.26, 32), m.cap); cap.position.y = 1.25; g.add(cap);
    return { g, h: 1.38, w: 0.54 };
  },
};

// A short product name for the label: no brand, no pack size.
function shortName(p) {
  let t = p.title.replace(new RegExp(p.brand, "i"), "").replace(/\b\d+(\.\d+)?\s?(ml|g|gm|l|kg)\b/gi, "").replace(/[|()\-–,]+/g, " ").replace(/\s+/g, " ").trim();
  const words = t.split(" ");
  let out = "";
  for (const w of words) { if ((out + " " + w).trim().length > 22) break; out = (out + " " + w).trim(); }
  return out || t.slice(0, 22);
}

function labelTexture(p, accent, renderer) {
  const c = document.createElement("canvas");
  c.width = 512; c.height = 320;
  const x = c.getContext("2d");
  x.fillStyle = "#FBF6F3"; x.fillRect(0, 0, 512, 320);
  x.fillStyle = accent; x.fillRect(0, 0, 512, 10); x.fillRect(0, 310, 512, 10);
  x.fillStyle = INK; x.textAlign = "center";
  x.font = '500 30px "Geist Mono", ui-monospace, monospace';
  x.fillText(p.brand.toLowerCase(), 256, 70);
  const name = shortName(p);
  let size = 62;
  x.font = `italic 400 ${size}px "Bodoni Moda", Didot, serif`;
  const words = name.split(" ");
  const lines = []; let cur = "";
  for (const w of words) { const t = (cur + " " + w).trim(); if (x.measureText(t).width > 440 && cur) { lines.push(cur); cur = w; } else cur = t; }
  lines.push(cur);
  if (lines.length > 2) { size = 46; x.font = `italic 400 ${size}px "Bodoni Moda", Didot, serif`; }
  lines.slice(0, 3).forEach((l, i, a) => x.fillText(l, 256, 175 - (a.length - 1) * size * 0.5 + i * size * 1.02));
  x.font = '400 24px "Geist Mono", ui-monospace, monospace';
  x.fillStyle = "#80606A";
  if (p.size) x.fillText(`${+p.size.toFixed(1)} ${p.size_unit}`, 256, 282);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
  return tex;
}

function softShadowTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const x = c.getContext("2d");
  const g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, "rgba(59,21,32,0.30)"); g.addColorStop(0.55, "rgba(59,21,32,0.10)"); g.addColorStop(1, "rgba(59,21,32,0)");
  x.fillStyle = g; x.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

const nextTask = () => new Promise(r => setTimeout(r, 0));

async function renderBottles(items, colorFor, { width = 320, height = 320, onImage = () => {} } = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true, powerPreference: "low-power" });
  } catch { return false; }
  renderer.setPixelRatio(1);
  renderer.setSize(width, height, false);
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  try { await Promise.all([document.fonts.load('italic 400 40px "Bodoni Moda"'), document.fonts.load('500 30px "Geist Mono"')]); } catch { /* labels fall back to system fonts */ }

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = env;
  scene.environmentIntensity = 0.55;
  pmrem.dispose();
  scene.add(new THREE.HemisphereLight(0xfff4ef, 0xe7c9c1, 0.9));
  const key = new THREE.PointLight(0xfff1e6, 22, 14, 1.6);
  key.position.set(-1.6, 2.6, 3.2);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffd9cf, 1.6);
  rim.position.set(3, 3, -3);
  scene.add(rim);

  const shadowTex = softShadowTexture();
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(1.7, 0.9), new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false, opacity: 0.7 }));
  shadow.rotation.x = -Math.PI / 2;
  scene.add(shadow);

  // One camera for every product, so a jar really is squatter than a dropper bottle.
  const camera = new THREE.PerspectiveCamera(24, width / height, 0.1, 30);
  camera.position.set(0, 1.05, 3.9);
  camera.lookAt(0, 0.6, 0);

  for (let i = 0; i < items.length; i++) {
    const p = items[i];
    const base = new THREE.Color(colorFor(p.brand_slug));
    const k = i % 4;                                  // a tonal range per brand: deep, mid, pale, porcelain
    const bodyColor = base.clone().lerp(PORCELAIN, [0.05, 0.38, 0.62, 0.8][k]);
    const label = labelTexture(p, colorFor(p.brand_slug), renderer);
    const mats = {
      body: new THREE.MeshPhysicalMaterial({ color: bodyColor, roughness: 0.16, metalness: 0, clearcoat: 1, clearcoatRoughness: 0.05, sheen: 0.3, sheenColor: bodyColor.clone().lerp(PORCELAIN, 0.6) }),
      cap: k % 2 ? new THREE.MeshStandardMaterial({ color: GOLD, metalness: 1, roughness: 0.22 })
                 : new THREE.MeshPhysicalMaterial({ color: base.clone().lerp(new THREE.Color(INK), 0.35), roughness: 0.3, clearcoat: 1 }),
      bulb: new THREE.MeshPhysicalMaterial({ color: base.clone().lerp(new THREE.Color(INK), 0.5), roughness: 0.45, clearcoat: 0.6 }),
      label: new THREE.MeshStandardMaterial({ map: label, roughness: 0.45, side: THREE.DoubleSide }),
    };
    const { g, h, w } = SHAPES[SHAPE_BY_CATEGORY[p.category] || "oil"](mats);
    g.scale.setScalar(Math.min(1.2 / h, 1.15 / w));
    g.rotation.y = (i % 2 ? -1 : 1) * 0.16;
    scene.add(g);
    renderer.render(scene, camera);
    const blob = await new Promise(res => renderer.domElement.toBlob(res, "image/webp", 0.9));
    if (blob) onImage(i, URL.createObjectURL(blob));
    scene.remove(g);
    g.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    Object.values(mats).forEach(m => m.dispose());
    label.dispose();
    await nextTask();                                 // let the carousel keep its frame rate
  }

  shadowTex.dispose();
  env.dispose();
  renderer.dispose();
  renderer.forceContextLoss();
  return true;
}

window.__renderBottles = renderBottles;
window.dispatchEvent(new Event("shelf3d-ready"));
