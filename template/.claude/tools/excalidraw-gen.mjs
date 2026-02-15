#!/usr/bin/env node

// excalidraw-gen.mjs v2.1 — JSON spec → Excalidraw format (zero deps)
// Supports two modes:
//   1. Explicit layout: nodes have x,y → converter only renders (recommended)
//   2. Auto layout: no x,y → BFS fallback (simple diagrams only)

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';
import { stdin } from 'process';

const COLORS = {
  orange: { bg: '#ffc078', stroke: '#e8590c' },
  blue:   { bg: '#a5d8ff', stroke: '#1971c2' },
  yellow: { bg: '#ffec99', stroke: '#f08c00' },
  green:  { bg: '#b2f2bb', stroke: '#2f9e44' },
  red:    { bg: '#ffc9c9', stroke: '#e03131' },
  purple: { bg: '#d0bfff', stroke: '#9c36b5' },
  gray:   { bg: '#e9ecef', stroke: '#868e96' },
  teal:   { bg: '#96f2d7', stroke: '#0c8599' }
};

const FONT = { title: 28, group: 20, node: 20, edge: 16 };
const CHAR_W = 0.62; // avg char width as fraction of fontSize (Helvetica)

// Lighten a hex color towards white (factor 0-1, higher = lighter)
function lightenColor(hex, factor = 0.5) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const lr = Math.round(r + (255 - r) * factor);
  const lg = Math.round(g + (255 - g) * factor);
  const lb = Math.round(b + (255 - b) * factor);
  return `#${lr.toString(16).padStart(2, '0')}${lg.toString(16).padStart(2, '0')}${lb.toString(16).padStart(2, '0')}`;
}

const DEFAULTS = {
  roughness: 0,
  fontFamily: 2, // Helvetica — clean, professional (1=Virgil handwritten, 2=Helvetica, 3=Cascadia mono)
  strokeWidth: 2,
  fillStyle: 'solid',
  opacity: 100,
  strokeColor: '#1e1e1e',
  backgroundColor: 'transparent'
};

let idCounter = 0;
const uid = () => `el_${idCounter++}`;

// --- Text measurement ---

function textWidth(text, fontSize) {
  const lines = text.split('\n');
  const maxLen = Math.max(...lines.map(l => l.length));
  return maxLen * fontSize * CHAR_W;
}

function textHeight(text, fontSize) {
  return text.split('\n').length * fontSize * 1.25;
}

// --- Base element factory ---

function el(id, type, x, y, overrides = {}) {
  return {
    id, type, x, y, angle: 0,
    strokeColor: DEFAULTS.strokeColor,
    backgroundColor: DEFAULTS.backgroundColor,
    fillStyle: DEFAULTS.fillStyle,
    strokeWidth: DEFAULTS.strokeWidth,
    strokeStyle: 'solid',
    roughness: DEFAULTS.roughness,
    opacity: DEFAULTS.opacity,
    fontFamily: DEFAULTS.fontFamily,
    updated: Date.now(),
    link: null, locked: false, groupIds: [],
    ...overrides
  };
}

// --- Layout: explicit or BFS fallback ---

function resolvePositions(nodes, edges, direction) {
  const hasExplicit = nodes.every(n => n.x != null && n.y != null);
  if (hasExplicit) {
    const positions = new Map();
    nodes.forEach(n => {
      const tw = textWidth(n.label, FONT.node);
      const th = textHeight(n.label, FONT.node);
      const w = n.w || Math.max(tw + 32, 120);
      const h = n.h || Math.max(th + 24, 60);
      // x,y in spec = CENTER of node → convert to top-left for rendering
      positions.set(n.id, { x: n.x - w / 2, y: n.y - h / 2, width: w, height: h });
    });
    return positions;
  }
  return bfsLayout(nodes, edges, direction);
}

function bfsLayout(nodes, edges, direction) {
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const adj = new Map(), inDeg = new Map();
  nodes.forEach(n => { adj.set(n.id, []); inDeg.set(n.id, 0); });
  edges.forEach(e => {
    if (adj.has(e.from)) adj.get(e.from).push(e.to);
    inDeg.set(e.to, (inDeg.get(e.to) || 0) + 1);
  });

  const roots = nodes.filter(n => inDeg.get(n.id) === 0).map(n => n.id);
  if (!roots.length && nodes.length) roots.push(nodes[0].id);

  const layers = new Map(), visited = new Set();
  const queue = roots.map(id => ({ id, layer: 0 }));
  while (queue.length) {
    const { id, layer } = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    if (!layers.has(layer)) layers.set(layer, []);
    layers.get(layer).push(id);
    (adj.get(id) || []).forEach(nId => {
      if (!visited.has(nId)) queue.push({ id: nId, layer: layer + 1 });
    });
  }
  // Orphans
  nodes.forEach(n => {
    if (!visited.has(n.id)) {
      const maxL = Math.max(...layers.keys(), 0);
      if (!layers.has(maxL + 1)) layers.set(maxL + 1, []);
      layers.get(maxL + 1).push(n.id);
    }
  });

  const isTB = direction !== 'LR';
  const positions = new Map();
  const sorted = [...layers.keys()].sort((a, b) => a - b);
  const layerSizes = new Map();
  sorted.forEach(layer => {
    let maxH = 0;
    layers.get(layer).forEach(id => {
      const n = nodeMap.get(id);
      const th = textHeight(n.label, FONT.node);
      const h = Math.max(th + 24, 60);
      if (h > maxH) maxH = h;
    });
    layerSizes.set(layer, maxH);
  });

  let cumY = 0;
  sorted.forEach(layer => {
    const ids = layers.get(layer);
    ids.forEach((id, idx) => {
      const n = nodeMap.get(id);
      const tw = textWidth(n.label, FONT.node);
      const th = textHeight(n.label, FONT.node);
      const w = Math.max(tw + 32, 120);
      const h = Math.max(th + 24, 60);
      const x = isTB ? (idx - ids.length / 2 + 0.5) * (w + 100) : cumY;
      const y = isTB ? cumY : (idx - ids.length / 2 + 0.5) * (h + 80);
      positions.set(id, { x: Math.round(x), y: Math.round(y), width: w, height: h });
    });
    cumY += layerSizes.get(layer) + 100;
  });

  return positions;
}

// --- Shape rendering ---

function renderShape(node, pos) {
  const color = COLORS[node.color] || COLORS.gray;
  const shape = node.shape || 'rect';
  let type = 'rectangle', roundness = { type: 3 }, strokeStyle = 'solid';

  if (shape === 'diamond')   { type = 'diamond'; roundness = { type: 2 }; }
  else if (shape === 'ellipse')  { type = 'ellipse'; roundness = null; }
  else if (shape === 'database') { strokeStyle = 'dashed'; }
  else if (shape === 'external') { strokeStyle = 'dashed'; }
  else if (shape === 'rounded')  { roundness = { type: 3, value: 16 }; }

  const shapeId = uid(), textId = uid();
  const { x, y, width: w, height: h } = pos;

  const tw = textWidth(node.label, FONT.node);
  const th = textHeight(node.label, FONT.node);

  // Database/external shapes get lighter fill to visually distinguish from solid shapes
  const isDashed = shape === 'database' || shape === 'external';
  const bg = isDashed ? lightenColor(color.bg, 0.5) : color.bg;

  const shapeEl = el(shapeId, type, x, y, {
    width: w, height: h,
    strokeColor: color.stroke,
    backgroundColor: bg,
    strokeStyle, roundness,
    boundElements: [{ id: textId, type: 'text' }]
  });

  const textEl = el(textId, 'text', x + (w - tw) / 2, y + (h - th) / 2, {
    width: tw, height: th,
    fontSize: FONT.node,
    text: node.label,
    textAlign: 'center',
    verticalAlign: 'middle',
    baseline: FONT.node,
    containerId: shapeId,
    originalText: node.label,
    autoResize: true,
    lineHeight: 1.25,
    strokeWidth: 0
  });

  return { shapeEl, textEl, shapeId };
}

// --- Arrow rendering ---

function renderArrow(edge, fromPos, toPos) {
  const fromCx = fromPos.x + fromPos.width / 2;
  const fromCy = fromPos.y + fromPos.height / 2;
  const toCx = toPos.x + toPos.width / 2;
  const toCy = toPos.y + toPos.height / 2;
  const rawDx = toCx - fromCx;
  const rawDy = toCy - fromCy;
  const dx = Math.abs(rawDx);
  const dy = Math.abs(rawDy);

  // Elbowed routing: "h" = horizontal-first, "v" = vertical-first
  const elbow = edge.elbow;

  let startX, startY, endX, endY, points;

  if (elbow === 'h') {
    // Horizontal first: exit side → horizontal → turn vertical → enter top/bottom
    const goingRight = rawDx > 0;
    const goingDown = rawDy > 0;
    startX = goingRight ? fromPos.x + fromPos.width : fromPos.x;
    startY = fromPos.y + fromPos.height / 2;
    endX = toPos.x + toPos.width / 2;
    endY = goingDown ? toPos.y : toPos.y + toPos.height;
    points = [[0, 0], [endX - startX, 0], [endX - startX, endY - startY]];
  } else if (elbow === 'v') {
    // Vertical first: exit top/bottom → vertical → turn horizontal → enter side
    const goingDown = rawDy > 0;
    const goingRight = rawDx > 0;
    startX = fromPos.x + fromPos.width / 2;
    startY = goingDown ? fromPos.y + fromPos.height : fromPos.y;
    endX = goingRight ? toPos.x : toPos.x + toPos.width;
    endY = toPos.y + toPos.height / 2;
    points = [[0, 0], [0, endY - startY], [endX - startX, endY - startY]];
  } else {
    // Straight line (default)
    const vertical = dy > dx * 0.3;
    if (vertical) {
      const goingDown = rawDy > 0;
      startX = fromPos.x + fromPos.width / 2;
      startY = goingDown ? fromPos.y + fromPos.height : fromPos.y;
      endX = toPos.x + toPos.width / 2;
      endY = goingDown ? toPos.y : toPos.y + toPos.height;
    } else {
      const goingRight = rawDx > 0;
      startX = goingRight ? fromPos.x + fromPos.width : fromPos.x;
      startY = fromPos.y + fromPos.height / 2;
      endX = goingRight ? toPos.x : toPos.x + toPos.width;
      endY = toPos.y + toPos.height / 2;
    }
    points = [[0, 0], [endX - startX, endY - startY]];
  }

  const arrowId = uid();
  const elements = [el(arrowId, 'arrow', startX, startY, {
    width: endX - startX,
    height: endY - startY,
    strokeStyle: edge.style === 'dashed' ? 'dashed' : 'solid',
    points,
    lastCommittedPoint: null,
    startBinding: { elementId: edge.fromId, focus: 0, gap: 5 },
    endBinding: { elementId: edge.toId, focus: 0, gap: 5 },
    startArrowhead: null,
    endArrowhead: 'arrow',
    roundness: { type: 2 }
  })];

  if (edge.label) {
    // Place label at the middle waypoint of the path
    const midIdx = Math.floor(points.length / 2);
    const midPt = points[midIdx];
    const lx = startX + midPt[0];
    const ly = startY + midPt[1];
    const lw = textWidth(edge.label, FONT.edge);
    elements.push(el(uid(), 'text', lx - lw / 2, ly - FONT.edge, {
      width: lw,
      height: FONT.edge * 1.5,
      strokeWidth: 0,
      fontSize: FONT.edge,
      text: edge.label,
      textAlign: 'center',
      verticalAlign: 'top',
      baseline: FONT.edge,
      containerId: null,
      originalText: edge.label,
      autoResize: true,
      lineHeight: 1.25
    }));
  }

  return { elements, arrowId };
}

// --- Group rendering ---

function renderGroup(group, positions) {
  const poses = group.nodes.map(id => positions.get(id)).filter(Boolean);
  if (!poses.length) return [];

  const pad = 40;
  const headerH = FONT.group * 1.5 + 10;
  const minX = Math.min(...poses.map(p => p.x)) - pad;
  const minY = Math.min(...poses.map(p => p.y)) - pad - headerH;
  const maxX = Math.max(...poses.map(p => p.x + p.width)) + pad;
  const maxY = Math.max(...poses.map(p => p.y + p.height)) + pad;
  const w = maxX - minX, h = maxY - minY;

  const color = COLORS[group.color] || COLORS.gray;
  const gId = uid();

  return [
    el(gId, 'rectangle', minX, minY, {
      width: w, height: h,
      strokeColor: color.stroke,
      backgroundColor: color.bg,
      strokeWidth: 1,
      strokeStyle: 'dashed',
      opacity: 25,
      roundness: { type: 3 }
    }),
    el(uid(), 'text', minX + 10, minY + 8, {
      width: w - 20,
      height: headerH,
      strokeColor: color.stroke,
      strokeWidth: 0,
      fontSize: FONT.group,
      text: group.label,
      textAlign: 'left',
      verticalAlign: 'top',
      baseline: FONT.group,
      containerId: null,
      originalText: group.label,
      autoResize: false,
      lineHeight: 1.25
    })
  ];
}

// --- Title ---

function renderTitle(title, positions) {
  const allPos = [...positions.values()];
  // Use median center-X (robust against outlier nodes like fan-out personas)
  const centerXs = allPos.map(p => p.x + p.width / 2).sort((a, b) => a - b);
  const mid = Math.floor(centerXs.length / 2);
  const cx = centerXs.length % 2 ? centerXs[mid] : (centerXs[mid - 1] + centerXs[mid]) / 2;
  const minY = Math.min(...allPos.map(p => p.y));
  const tw = textWidth(title, FONT.title);
  const w = Math.max(tw, 300);

  return el(uid(), 'text', cx - w / 2, minY - 70, {
    width: w,
    height: FONT.title * 1.5,
    strokeWidth: 0,
    fontSize: FONT.title,
    text: title,
    textAlign: 'center',
    verticalAlign: 'top',
    baseline: FONT.title,
    containerId: null,
    originalText: title,
    autoResize: true,
    lineHeight: 1.25
  });
}

// --- Main conversion ---

function convert(spec) {
  const elements = [];
  const positions = resolvePositions(spec.nodes, spec.edges || [], spec.direction || 'TB');

  // Title
  if (spec.title) elements.push(renderTitle(spec.title, positions));

  // Groups (background, rendered first)
  if (spec.groups) {
    spec.groups.forEach(g => elements.push(...renderGroup(g, positions)));
  }

  // Nodes
  const idMap = new Map();
  spec.nodes.forEach(node => {
    const pos = positions.get(node.id);
    if (!pos) return;
    const { shapeEl, textEl, shapeId } = renderShape(node, pos);
    idMap.set(node.id, shapeId);
    elements.push(shapeEl, textEl);
  });

  // Edges
  (spec.edges || []).forEach(edge => {
    const fromPos = positions.get(edge.from);
    const toPos = positions.get(edge.to);
    if (!fromPos || !toPos) return;

    const edgeData = { ...edge, fromId: idMap.get(edge.from), toId: idMap.get(edge.to) };
    const { elements: arrowEls, arrowId } = renderArrow(edgeData, fromPos, toPos);

    // Register arrow on shapes
    const fromShape = elements.find(e => e.id === edgeData.fromId);
    const toShape = elements.find(e => e.id === edgeData.toId);
    if (fromShape?.boundElements) fromShape.boundElements.push({ id: arrowId, type: 'arrow' });
    if (toShape?.boundElements) toShape.boundElements.push({ id: arrowId, type: 'arrow' });

    elements.push(...arrowEls);
  });

  return {
    type: 'excalidraw',
    version: 2,
    source: 'dld-diagram-skill',
    elements,
    appState: { gridSize: null, viewBackgroundColor: '#ffffff' },
    files: {}
  };
}

// --- CLI ---

async function readStdin() {
  const chunks = [];
  for await (const chunk of stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf-8');
}

(async () => {
  try {
    const args = process.argv.slice(2);
    let input, outputFile;
    if (args.length >= 2) { input = readFileSync(args[0], 'utf-8'); outputFile = args[1]; }
    else if (args.length === 1 && !process.stdin.isTTY) { input = await readStdin(); outputFile = args[0]; }
    else if (args.length === 1) { input = readFileSync(args[0], 'utf-8'); outputFile = null; }
    else { input = await readStdin(); outputFile = null; }

    const output = JSON.stringify(convert(JSON.parse(input)), null, 2);
    if (outputFile) { mkdirSync(dirname(outputFile), { recursive: true }); writeFileSync(outputFile, output, 'utf-8'); }
    else console.log(output);
  } catch (err) { console.error('Error:', err.message); process.exit(1); }
})();
