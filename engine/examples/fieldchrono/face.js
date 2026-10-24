// FIELD 01: an original two-register field watch. Worked example for the Dialtwin engine contract
// (engine/CONTRACT.md). It shows every feature a typical face needs: two layouts (full dial, or with a
// painted count-up bezel), colourways, applied indices, live registers, a date window, sweep seconds
// and an Always-On plate in two tints.
//
// Builds SVG markup for each layer so the same source drives the live preview, the PNG renders the
// critics look at, and the WFF assets. Coordinates are polar around the dial centre (0,0); the outer
// group maps that onto the 480 canvas. Angles are clock degrees (0 = 12 o'clock, clockwise).

(function (global) {
  const rad = (deg) => (deg * Math.PI) / 180;
  const px = (r, deg) => [r * Math.sin(rad(deg)), -r * Math.cos(rad(deg))];
  const f = (n) => +n.toFixed(2);

  // ---------------------------------------------------------------- geometry
  const G = {
    bezelOuter: 240, bezelInner: 206,
    flangeOuter: 206, flangeInner: 186, flangeNum: 196.5,
    idxOuter: 179, idxInner: 147, idxW: 11,
    reg: { dist: 92, r: 40 },
    date: { x: 0, y: 124, w: 38, h: 28 },
    hub: 12,
  };

  // ---------------------------------------------------------------- palettes
  const P = {
    slate: {
      dialIn: '#3b434c', dialOut: '#252b32', grain: 0.10,
      ink: '#e9e5d9', ink2: '#a9afb5', accent: '#ff6a2a',
      lume: '#f2edda', idxRim: '#c7cacd',
      flangeIn: '#171b20', flangeOut: '#232930', flangeInk: '#c8c5bb',
      regFill: '#20252b', regGroove: 'rgba(255,255,255,.05)', regInk: '#d8d5cb', regRing: '#11141a',
      handRim: '#c7cacd', handFill: '#f2edda', hubFill: '#2a2f36', halo: 0.6,
      dateBg: '#111418', dateFrame: '#c7cacd', dateInk: '#ffeae6dc',
      bezelIn: '#101215', bezelOut: '#1a1d21', bezelInk: '#e3dfd3', bezelEdge: '#6c7176',
    },
    sand: {
      dialIn: '#f0eadb', dialOut: '#dbd2be', grain: 0.08,
      ink: '#1e1f22', ink2: '#56585c', accent: '#cf3a28',
      lume: '#fbf8ee', idxRim: '#25272a',
      flangeIn: '#d7cfbc', flangeOut: '#e6dfcf', flangeInk: '#3a3c40',
      regFill: '#e3dbc9', regGroove: 'rgba(0,0,0,.05)', regInk: '#2a2b2e', regRing: '#b9b09c',
      handRim: '#1f2124', handFill: '#fbf8ee', hubFill: '#1f2124', halo: 0.35,
      dateBg: '#fbf9f3', dateFrame: '#25272a', dateInk: '#ff1d1d1f',
      bezelIn: '#18191b', bezelOut: '#232427', bezelInk: '#e8e3d4', bezelEdge: '#76787b',
    },
  };

  // Always-On tints. Same geometry for both; only colours change.
  const AODS = {
    green: { lume: '#79f79a', lumeStatic: '#4fc070', lumeDim: '#3f9a58', ink: '#347e48', rim: '#2a5a36', hubFill: '#0b1a10', accent: '#5fd884' },
    red: { lume: '#ff5040', lumeStatic: '#d03a2e', lumeDim: '#8e2820', ink: '#9a3027', rim: '#5c1a15', hubFill: '#1a0908', accent: '#ff7a4a' },
  };
  let AOD = AODS.green;

  const NUM = "'Oxanium', 'ShareTechMono', monospace";
  const WORD = "'Michroma', 'Oxanium', sans-serif";
  const LABEL = "'BarlowCondensed', 'RobotoCondensed', sans-serif";

  // ------------------------------------------------------------- primitives
  function ring(r1, r2, fill, extra = '') {
    return `<path fill-rule="evenodd" fill="${fill}" ${extra} d="M ${r2} 0 A ${r2} ${r2} 0 1 0 ${-r2} 0 A ${r2} ${r2} 0 1 0 ${r2} 0 Z M ${r1} 0 A ${r1} ${r1} 0 1 1 ${-r1} 0 A ${r1} ${r1} 0 1 1 ${r1} 0 Z"/>`;
  }
  // text at a polar position, rotated to read radially, flipped on the lower half so it is never upside down
  function polarText(str, r, deg, size, fill, font, weight = 400, flip = true, ls = 0) {
    const [x, y] = px(r, deg);
    let rot = deg;
    if (flip && deg > 90 && deg < 270) rot = deg - 180;
    return `<text x="${f(x)}" y="${f(y)}" transform="rotate(${f(rot)} ${f(x)} ${f(y)})" font-family="${font}" font-weight="${weight}" font-size="${size}" fill="${fill}" text-anchor="middle" dominant-baseline="central" letter-spacing="${ls}">${str}</text>`;
  }
  function text(str, x, y, size, fill, font, ls = 0, extra = '') {
    return `<text x="${f(x)}" y="${f(y)}" font-family="${font}" font-size="${size}" fill="${fill}" text-anchor="middle" dominant-baseline="central" letter-spacing="${ls}" ${extra}>${str}</text>`;
  }

  // ------------------------------------------------------------------ defs
  function defs(p, id) {
    return `<defs>
      <radialGradient id="${id}dial" cx="0" cy="0" r="${G.flangeInner}" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="${p.dialIn}"/><stop offset="1" stop-color="${p.dialOut}"/>
      </radialGradient>
      <radialGradient id="${id}flange" cx="0" cy="0" r="${G.flangeOuter}" gradientUnits="userSpaceOnUse">
        <stop offset="${f(G.flangeInner / G.flangeOuter)}" stop-color="${p.flangeIn}"/><stop offset="1" stop-color="${p.flangeOut}"/>
      </radialGradient>
      <radialGradient id="${id}bez" cx="0" cy="0" r="${G.bezelOuter}" gradientUnits="userSpaceOnUse">
        <stop offset="${f(G.bezelInner / G.bezelOuter)}" stop-color="${p.bezelIn}"/><stop offset="1" stop-color="${p.bezelOut}"/>
      </radialGradient>
      <filter id="${id}grain" x="-50%" y="-50%" width="200%" height="200%">
        <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" seed="11" result="n"/>
        <feColorMatrix type="saturate" values="0" in="n" result="g"/>
        <feComponentTransfer in="g" result="g2"><feFuncA type="linear" slope="0" intercept="${p.grain}"/></feComponentTransfer>
        <feComposite in="g2" in2="SourceGraphic" operator="in"/>
      </filter>
      <filter id="${id}shadow" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="0" stdDeviation="1.2" flood-color="#000" flood-opacity=".5"/>
      </filter>
      <filter id="${id}hshadow" x="-40%" y="-20%" width="180%" height="140%">
        <feDropShadow dx="0" dy="0" stdDeviation="1.8" flood-color="#000" flood-opacity="${p.halo}"/>
      </filter>
      <filter id="${id}glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="1.4" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>`;
  }

  // ------------------------------------------------------------------ bezel
  // 60-minute count-up insert: numerals every 10, dashes for the first 15 minutes, lume pip at 12.
  function bezel(p, id) {
    let s = ring(G.bezelInner, G.bezelOuter, `url(#${id}bez)`);
    s += `<circle r="${G.bezelOuter - 1}" fill="none" stroke="${p.bezelEdge}" stroke-width="2"/>`;
    for (let m = 1; m < 60; m++) {
      if (m % 10 === 0) continue;
      const a = m * 6;
      if (m < 15) {
        const [x1, y1] = px(m % 5 === 0 ? 212 : 216, a), [x2, y2] = px(230, a);
        s += `<line x1="${f(x1)}" y1="${f(y1)}" x2="${f(x2)}" y2="${f(y2)}" stroke="${p.bezelInk}" stroke-width="${m % 5 === 0 ? 3 : 1.8}" stroke-linecap="round"/>`;
      } else if (m % 5 === 0) {
        const [x, y] = px(222, a);
        s += `<circle cx="${f(x)}" cy="${f(y)}" r="3.2" fill="${p.bezelInk}"/>`;
      }
    }
    for (const n of [10, 20, 30, 40, 50]) s += polarText(String(n), 222, n * 6, 20, p.bezelInk, NUM, 600, true, 0.5);
    s += `<path d="M -11 -233 L 11 -233 L 0 -212 Z" fill="${p.bezelInk}"/>`;
    s += `<circle cx="0" cy="-226" r="3.4" fill="${p.lume}"/>`;
    s += `<circle r="${G.bezelInner}" fill="none" stroke="rgba(0,0,0,.6)" stroke-width="2"/>`;
    return s;
  }

  // ----------------------------------------------------------------- flange
  // sloped rehaut with a minute track and five-minute numerals
  function flange(p, id) {
    let s = ring(G.flangeInner, G.flangeOuter, `url(#${id}flange)`);
    for (let m = 0; m < 60; m++) {
      const a = m * 6;
      if (m % 5 === 0) {
        const n = m === 0 ? '60' : String(m).padStart(2, '0');
        s += polarText(n, G.flangeNum, a, 12.5, p.flangeInk, NUM, 600, true, 0.3);
      } else {
        const [x1, y1] = px(G.flangeInner + 3, a), [x2, y2] = px(G.flangeInner + 11, a);
        s += `<line x1="${f(x1)}" y1="${f(y1)}" x2="${f(x2)}" y2="${f(y2)}" stroke="${p.flangeInk}" stroke-width="1.6"/>`;
      }
    }
    s += `<circle r="${G.flangeInner}" fill="none" stroke="rgba(0,0,0,.35)" stroke-width="1.2"/>`;
    return s;
  }

  // ------------------------------------------------------------- dial body
  function index(p, id, a, aod) {
    const w = G.idxW / 2, o = G.idxOuter, i = G.idxInner;
    if (aod) return `<rect x="${-w + 2}" y="${-o + 2}" width="${G.idxW - 4}" height="${o - i - 4}" rx="1.5" transform="rotate(${a})" fill="${AOD.lumeStatic}"/>`;
    return `<g transform="rotate(${a})"><rect x="${-w}" y="${-o}" width="${G.idxW}" height="${o - i}" rx="2" fill="${p.idxRim}" filter="url(#${id}shadow)"/>` +
      `<rect x="${-w + 2}" y="${-o + 2}" width="${G.idxW - 4}" height="${o - i - 4}" rx="1.5" fill="${p.lume}"/></g>`;
  }

  function register(p, id, cx, label) {
    const r = G.reg.r;
    let s = `<g transform="translate(${cx} 0)">`;
    s += `<circle r="${r + 1.5}" fill="${p.regRing}"/><circle r="${r}" fill="${p.regFill}"/>`;
    for (let k = 6; k < r; k += 2.4) s += `<circle r="${f(k)}" fill="none" stroke="${p.regGroove}" stroke-width="1"/>`;
    for (let t = 0; t < 20; t++) {
      const major = t % 5 === 0, a = t * 18;
      const [x1, y1] = px(major ? r - 11 : r - 7, a), [x2, y2] = px(r - 3, a);
      s += `<line x1="${f(x1)}" y1="${f(y1)}" x2="${f(x2)}" y2="${f(y2)}" stroke="${p.regInk}" stroke-width="${major ? 2.4 : 1.5}" stroke-linecap="round"/>`;
    }
    s += text(label, 0, 17, 11, p.regInk, LABEL, 1.2);
    return s + '</g>';
  }

  function brand(p) {
    // the app's own wordmark: an example face must never carry another maker's name
    return text('DIALTWIN', 0, -84, 15, p.ink, WORD, 2.2) +
      text('FIELD 01', 0, -64, 12, p.accent, LABEL, 2.5, `font-weight="600"`);
  }

  function dateFrame(p, aod) {
    const { x, y, w, h } = G.date;
    if (aod) return `<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="3" fill="none" stroke="${AOD.lumeDim}" stroke-opacity=".7" stroke-width="1.5"/>`;
    return `<rect x="${x - w / 2 - 2}" y="${y - h / 2 - 2}" width="${w + 4}" height="${h + 4}" rx="4" fill="${p.dateFrame}"/>` +
      `<rect x="${x - w / 2}" y="${y - h / 2}" width="${w}" height="${h}" rx="3" fill="${p.dateBg}"/>`;
  }

  function dialBody(p, id) {
    let s = `<circle r="${G.flangeInner + 0.5}" fill="url(#${id}dial)"/>`;
    s += `<circle r="${G.flangeInner}" fill="#808080" filter="url(#${id}grain)"/>`;
    for (let h = 1; h < 12; h++) if (h !== 6) s += index(p, id, h * 30, false);
    s += index(p, id, 180, false).replace(`height="${G.idxOuter - G.idxInner}"`, `height="22"`).replace(`height="${G.idxOuter - G.idxInner - 4}"`, 'height="18"');
    s += text('12', 0, -158, 36, p.ink, NUM, 0, `font-weight="600" stroke="${p.ink}" stroke-width=".5"`);
    s += register(p, id, -G.reg.dist, 'PWR') + register(p, id, G.reg.dist, 'STEPS');
    s += brand(p) + dateFrame(p, false);
    return s;
  }

  // ------------------------------------------------------------------ hands
  // Each hand is drawn pointing at 12 around its own pivot (0,0).
  function sword(len, w, tail, rim, fill, frame) {
    const outer = `M ${f(-w * 0.55)} ${tail} L ${-w} -22 L 0 ${-len} L ${w} -22 L ${f(w * 0.55)} ${tail} Z`;
    const iw = w - frame;
    const inner = `M ${f(-iw)} -34 L 0 ${f(-(len - frame * 3.2))} L ${f(iw)} -34 Z`;
    return `<path d="${outer}" fill="${rim}" stroke-linejoin="round"/><path d="${inner}" fill="${fill}"/>`;
  }

  function hands(p, id, aod) {
    const H = {};
    const rim = aod ? AOD.rim : p.handRim;
    const fill = aod ? AOD.lume : p.handFill;
    const sh = aod ? '' : `filter="url(#${id}hshadow)"`;
    H.hour = `<g ${sh}>${sword(116, 9, 18, rim, fill, 2.6)}</g>`;
    H.minute = `<g ${sh}>${sword(170, 7, 22, rim, fill, 2.3)}</g>`;
    const acc = aod ? AOD.accent : p.accent;
    H.second = `<g ${sh}><rect x="-1.2" y="-178" width="2.4" height="218" rx="1.2" fill="${acc}"/>` +
      `<circle cy="-132" r="6.5" fill="${p.lume}" stroke="${acc}" stroke-width="2.4"/><circle cy="34" r="6" fill="${acc}"/></g>`;
    const regHand = `<g ${sh}><path d="M -1.8 8 L -1.8 -24 L 0 -33 L 1.8 -24 L 1.8 8 Z" fill="${p.accent}"/><circle r="4.5" fill="${p.regInk}"/><circle r="1.6" fill="${p.regFill}"/></g>`;
    H.regLeft = regHand;
    H.regRight = regHand;
    H.hub = aod
      ? `<circle r="5.5" fill="${AOD.hubFill}" stroke="${AOD.lumeDim}" stroke-width="1.5"/>`
      : `<g ${sh}><circle r="${G.hub}" fill="${p.hubFill}"/><circle r="7" fill="${p.accent}"/><circle r="2.4" fill="${p.hubFill}"/></g>`;
    return H;
  }

  // ------------------------------------------------------------ AOD plate
  // black, ~8-12 % lit: indices, the 12, register rims and the date frame, all dimmer than the hands
  function aodPlate(p, id) {
    let s = `<circle r="240" fill="#000"/>`;
    s += `<g filter="url(#${id}glow)">`;
    for (let h = 1; h < 12; h++) if (h !== 6) s += index(p, id, h * 30, true);
    s += '</g>';
    s += text('12', 0, -158, 36, AOD.ink, NUM, 0, `font-weight="600"`);
    for (const cx of [-G.reg.dist, G.reg.dist]) {
      s += `<circle cx="${cx}" cy="0" r="${G.reg.r}" fill="none" stroke="${AOD.lumeDim}" stroke-opacity=".6" stroke-width="1.5"/>`;
    }
    s += dateFrame(p, true);
    return s;
  }

  // ---------------------------------------------------------------- public
  const manifest = {
    name: 'FIELD 01',
    variants: [
      { id: 'slate', label: 'Slate' },
      { id: 'sand', label: 'Sand' },
    ],
    layouts: [
      { id: 'dial', label: 'Full dial' },
      { id: 'bezel', label: 'Count-up bezel' },
    ],
    aodTints: [
      { id: 'green', label: 'Green lume' },
      { id: 'red', label: 'Red night vision' },
    ],
    // paint order, bottom to top; pivot in dial units relative to centre (before layout scale)
    hands: [
      { id: 'regLeft', kind: 'battery', pivot: [-G.reg.dist, 0] },
      { id: 'regRight', kind: 'steps', pivot: [G.reg.dist, 0] },
      { id: 'hour', kind: 'hour' },
      { id: 'minute', kind: 'minute' },
      { id: 'second', kind: 'second', sweep: '10' },
      { id: 'hub', kind: 'static' },
    ],
    aodHands: ['hour', 'minute', 'hub'],
    dateWindow: {
      x: G.date.x, y: G.date.y, w: G.date.w, h: G.date.h, size: 21, font: 'Oxanium.ttf', format: 'DAY_Z',
      colors: { slate: P.slate.dateInk, sand: P.sand.dateInk },
      aodColors: { green: '#ff3f9a58', red: '#ff8e2820' },
    },
    photoLayout: 'bezel',
    photoPose: { time: '10:09:30' },
    previewTime: '10:09:30',
  };

  function build(opts) {
    const p = P[opts.variant];
    AOD = AODS[opts.aod || 'green'];
    const id = `${opts.variant}_`;
    const bezelOn = opts.layout === 'bezel';
    const scale = bezelOn ? 1 : 240 / G.flangeOuter;
    const wrap = (inner) => `<g transform="translate(240 240) scale(${f(scale)})">${inner}</g>`;
    const svg = (inner) => `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="480" height="480" viewBox="0 0 480 480">${defs(p, id)}${wrap(inner)}</svg>`;
    const plate = (bezelOn ? bezel(p, id) : '') + flange(p, id) + dialBody(p, id);
    return {
      scale, svg,
      plate: svg(plate),
      aod: svg(aodPlate(p, id)),
      hands: hands(p, id, false),
      aodHands: hands(p, id, true),
    };
  }

  global.WatchFace = { build, manifest };
})(typeof window !== 'undefined' ? window : globalThis);
