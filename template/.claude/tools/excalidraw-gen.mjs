#!/usr/bin/env node

// excalidraw-gen.mjs — simplified JSON spec → Excalidraw format (zero deps)

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';
import { stdin } from 'process';

const COLORS = {
  orange: { bg: '#ffc078', stroke: '#e8590c' },
  blue: { bg: '#a5d8ff', stroke: '#1971c2' },
  yellow: { bg: '#ffec99', stroke: '#f08c00' },
  green: { bg: '#b2f2bb', stroke: '#2f9e44' },
  red: { bg: '#ffc9c9', stroke: '#e03131' },
  purple: { bg: '#d0bfff', stroke: '#9c36b5' },
  gray: { bg: '#e9ecef', stroke: '#868e96' },
  teal: { bg: '#96f2d7', stroke: '#0c8599' }
};

const FONT_SIZES = {
  title: 28,
  group: 24,
  node: 20,
  edge: 14
};

const LAYOUT = {
  nodeMinWidth: 150,
  nodeMaxWidth: 320,
  nodeHeight: 60,
  nodeHeightMulti: 80,
  horizontalGap: 80,
  verticalGap: 50,
  gridSnap: 50,
  groupPadding: 30,
  arrowGap: 5
};

const DEFAULTS = {
  roughness: 0,
  fontFamily: 2, // Nunito
  strokeWidth: 2,
  fillStyle: 'solid',
  opacity: 100,
  strokeColor: '#343a40',
  backgroundColor: 'transparent'
};

let idCounter = 0;
function generateId() {
  return `el_${idCounter++}`;
}

function snapToGrid(value) {
  return Math.round(value / LAYOUT.gridSnap) * LAYOUT.gridSnap;
}

function calcTextWidth(text, fontSize) {
  const avgCharWidth = fontSize * 0.6;
  const lines = text.split('\n');
  const maxLineLength = Math.max(...lines.map(l => l.length));
  return Math.min(
    Math.max(maxLineLength * avgCharWidth, LAYOUT.nodeMinWidth),
    LAYOUT.nodeMaxWidth
  );
}

function calcTextHeight(text, fontSize) {
  const lines = text.split('\n');
  return lines.length > 1 ? LAYOUT.nodeHeightMulti : LAYOUT.nodeHeight;
}

function bfsLayout(nodes, edges, direction) {
  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const adjacency = new Map(), inDegree = new Map();

  nodes.forEach(n => { adjacency.set(n.id, []); inDegree.set(n.id, 0); });
  edges.forEach(e => { adjacency.get(e.from).push(e.to); inDegree.set(e.to, (inDegree.get(e.to) || 0) + 1); });

  const roots = nodes.filter(n => inDegree.get(n.id) === 0).map(n => n.id);
  if (!roots.length && nodes.length) roots.push(nodes[0].id);

  const layers = new Map(), visited = new Set();
  const queue = roots.map(id => ({ id, layer: 0 }));

  while (queue.length) {
    const { id, layer } = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    if (!layers.has(layer)) layers.set(layer, []);
    layers.get(layer).push(id);
    (adjacency.get(id) || []).forEach(nId => !visited.has(nId) && queue.push({ id: nId, layer: layer + 1 }));
  }

  nodes.forEach(n => {
    if (!visited.has(n.id)) {
      const maxLayer = Math.max(...layers.keys(), 0);
      if (!layers.has(maxLayer + 1)) layers.set(maxLayer + 1, []);
      layers.get(maxLayer + 1).push(n.id);
    }
  });

  const positions = new Map(), isTB = direction === 'TB';
  layers.forEach((nodeIds, layer) => {
    nodeIds.forEach((nodeId, idx) => {
      const node = nodeMap.get(nodeId);
      const width = calcTextWidth(node.label, FONT_SIZES.node);
      const height = calcTextHeight(node.label, FONT_SIZES.node);
      const [x, y] = isTB
        ? [snapToGrid((idx - nodeIds.length / 2 + 0.5) * (width + LAYOUT.horizontalGap)), snapToGrid(layer * (height + LAYOUT.verticalGap))]
        : [snapToGrid(layer * (width + LAYOUT.horizontalGap)), snapToGrid((idx - nodeIds.length / 2 + 0.5) * (height + LAYOUT.verticalGap))];
      positions.set(nodeId, { x, y, width, height });
    });
  });

  return positions;
}

function createShape(node, x, y, width, height) {
  const color = COLORS[node.color] || COLORS.gray;
  const shape = node.shape || 'rect';
  let type = 'rectangle', roundness = { type: 3 }, strokeStyle = 'solid';

  if (shape === 'diamond') { type = 'diamond'; roundness = { type: 2 }; }
  else if (shape === 'ellipse') { type = 'ellipse'; roundness = null; }
  else if (shape === 'external') strokeStyle = 'dashed';
  else if (shape === 'database') { color.bg = COLORS.purple.bg; color.stroke = COLORS.purple.stroke; }

  const shapeId = generateId(), textId = generateId();
  const sx = snapToGrid(x), sy = snapToGrid(y), sw = snapToGrid(width), sh = snapToGrid(height);

  return {
    shape: baseElement(shapeId, type, sx, sy, {
      width: sw, height: sh,
      strokeColor: color.stroke,
      backgroundColor: color.bg,
      strokeStyle, roundness,
      boundElements: [{ id: textId, type: 'text' }]
    }),
    text: createBoundText(
      shape === 'database' ? `DB:\n${node.label}` : node.label,
      shapeId, sx, sy, sw, sh, FONT_SIZES.node, textId
    )
  };
}

function baseElement(id, type, x, y, overrides = {}) {
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
    link: null,
    locked: false,
    groupIds: [],
    ...overrides
  };
}

function createBoundText(text, containerId, x, y, width, height, fontSize, textId) {
  return baseElement(textId || generateId(), 'text', x + width / 2, y + height / 2, {
    width, height, fontSize, text,
    textAlign: 'center',
    verticalAlign: 'middle',
    baseline: fontSize,
    containerId,
    originalText: text,
    autoResize: true,
    lineHeight: 1.25
  });
}

function createArrow(edge, fromPos, toPos) {
  const isTB = Math.abs(toPos.y - fromPos.y) > Math.abs(toPos.x - fromPos.x);
  const [startX, startY, endX, endY] = isTB
    ? [fromPos.x + fromPos.width / 2, fromPos.y + fromPos.height, toPos.x + toPos.width / 2, toPos.y]
    : [fromPos.x + fromPos.width, fromPos.y + fromPos.height / 2, toPos.x, toPos.y + toPos.height / 2];

  const elements = [baseElement(generateId(), 'arrow', startX, startY, {
    width: endX - startX,
    height: endY - startY,
    strokeStyle: edge.style === 'dashed' ? 'dashed' : 'solid',
    points: [[0, 0], [endX - startX, endY - startY]],
    lastCommittedPoint: null,
    startBinding: { elementId: edge.fromId, focus: 0, gap: LAYOUT.arrowGap },
    endBinding: { elementId: edge.toId, focus: 0, gap: LAYOUT.arrowGap },
    startArrowhead: null,
    endArrowhead: 'arrow',
    roundness: { type: 2 }
  })];

  if (edge.label) {
    const [labelX, labelY] = [(startX + endX) / 2, (startY + endY) / 2];
    elements.push(baseElement(generateId(), 'text', labelX, labelY - FONT_SIZES.edge, {
      width: calcTextWidth(edge.label, FONT_SIZES.edge),
      height: FONT_SIZES.edge * 1.5,
      backgroundColor: '#ffffff',
      strokeWidth: 0,
      fontSize: FONT_SIZES.edge,
      text: edge.label,
      textAlign: 'center',
      verticalAlign: 'top',
      baseline: FONT_SIZES.edge,
      containerId: null,
      originalText: edge.label,
      autoResize: true,
      lineHeight: 1.25
    }));
  }

  return elements;
}

function createGroup(group, positions) {
  const nodePositions = group.nodes.map(nId => positions.get(nId)).filter(p => p);
  if (nodePositions.length === 0) return [];

  const minX = Math.min(...nodePositions.map(p => p.x));
  const minY = Math.min(...nodePositions.map(p => p.y));
  const maxX = Math.max(...nodePositions.map(p => p.x + p.width));
  const maxY = Math.max(...nodePositions.map(p => p.y + p.height));

  const x = minX - LAYOUT.groupPadding;
  const y = minY - LAYOUT.groupPadding - FONT_SIZES.group - 10;
  const width = maxX - minX + 2 * LAYOUT.groupPadding;
  const height = maxY - minY + 2 * LAYOUT.groupPadding + FONT_SIZES.group + 10;

  const color = COLORS[group.color] || COLORS.gray;
  const groupId = generateId(), textId = generateId();
  const sx = snapToGrid(x), sy = snapToGrid(y), sw = snapToGrid(width), sh = snapToGrid(height);

  return [
    baseElement(groupId, 'rectangle', sx, sy, {
      width: sw, height: sh,
      strokeColor: color.stroke,
      backgroundColor: color.bg,
      strokeWidth: 1,
      strokeStyle: 'dashed',
      opacity: 30,
      roundness: { type: 3 },
      boundElements: [{ id: textId, type: 'text' }]
    }),
    baseElement(textId, 'text', sx + 10, sy + 10, {
      width: sw - 20,
      height: FONT_SIZES.group * 1.5,
      strokeColor: color.stroke,
      strokeWidth: 0,
      fontSize: FONT_SIZES.group,
      text: group.label,
      textAlign: 'left',
      verticalAlign: 'top',
      baseline: FONT_SIZES.group,
      containerId: null,
      originalText: group.label,
      autoResize: false,
      lineHeight: 1.25
    })
  ];
}

function createTitle(title, centerX = 0, topY = 0) {
  const titleWidth = Math.max(calcTextWidth(title, FONT_SIZES.title), 400);
  return baseElement(generateId(), 'text', snapToGrid(centerX - titleWidth / 2), snapToGrid(topY - 80), {
    width: titleWidth,
    height: FONT_SIZES.title * 1.5,
    strokeWidth: 0,
    fontSize: FONT_SIZES.title,
    text: title,
    textAlign: 'center',
    verticalAlign: 'top',
    baseline: FONT_SIZES.title,
    containerId: null,
    originalText: title,
    autoResize: true,
    lineHeight: 1.25
  });
}

function convert(spec) {
  const elements = [];

  const positions = bfsLayout(spec.nodes, spec.edges, spec.direction || 'TB');

  if (spec.title) {
    const allPos = [...positions.values()];
    const minX = Math.min(...allPos.map(p => p.x));
    const maxX = Math.max(...allPos.map(p => p.x + p.width));
    const minY = Math.min(...allPos.map(p => p.y));
    const centerX = (minX + maxX) / 2;
    elements.push(createTitle(spec.title, centerX, minY));
  }

  if (spec.groups) {
    spec.groups.forEach(group => elements.push(...createGroup(group, positions)));
  }

  const nodeIdMap = new Map();
  spec.nodes.forEach(node => {
    const pos = positions.get(node.id);
    if (!pos) return;

    const { shape, text } = createShape(node, pos.x, pos.y, pos.width, pos.height);
    nodeIdMap.set(node.id, shape.id);
    elements.push(shape, text);
  });

  spec.edges.forEach(edge => {
    const fromPos = positions.get(edge.from);
    const toPos = positions.get(edge.to);
    if (!fromPos || !toPos) return;

    const edgeWithIds = {
      ...edge,
      fromId: nodeIdMap.get(edge.from),
      toId: nodeIdMap.get(edge.to)
    };
    const arrowElements = createArrow(edgeWithIds, fromPos, toPos);
    const arrowId = arrowElements[0].id;

    const fromShape = elements.find(e => e.id === edgeWithIds.fromId);
    const toShape = elements.find(e => e.id === edgeWithIds.toId);
    if (fromShape) fromShape.boundElements.push({ id: arrowId, type: 'arrow' });
    if (toShape) toShape.boundElements.push({ id: arrowId, type: 'arrow' });

    elements.push(...arrowElements);
  });

  return {
    type: 'excalidraw',
    version: 2,
    source: 'dld-diagram-skill',
    elements,
    appState: {
      gridSize: null,
      viewBackgroundColor: '#ffffff'
    },
    files: {}
  };
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf-8');
}

// Usage: input.json output | stdin → output | stdin → stdout
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
