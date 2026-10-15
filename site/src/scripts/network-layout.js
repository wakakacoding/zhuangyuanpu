/**
 * 关系网络的力导向布局（纯计算，无 DOM 依赖 —— 可在 Node 下直接跑回归测试）
 *
 * 算法：Fruchterman–Reingold 变体，不引任何第三方库
 *   · 斥力   k²/d      （所有活跃节点两两相斥）
 *   · 引力   d²/k      （沿边相吸）
 *   · 向心   g·(p−中心)（弱，防连通分量飘散出画布）
 *   · 降温   t = t0·(1 − i/iters)^1.5，每轮位移按 t 截断（verlet 式限步，保证收敛不炸）
 * 布局完成后位置即冻结（页面不再跑动画帧），与「迭代 200 次后静止」一致。
 *
 * 布点确定：初始位置全部由数据推导（不掷随机数），同一份数据每次构建/刷新得同一张图。
 *   状元层：按科年升序排到一个圆环上 —— 年代相近者先天相邻，布局出来自然形成时代簇。
 *   名士层：落在其关联状元的质心处，即「先放到他认识的人中间」，再由力导向微调。
 */

export const DEFAULT_W = 1200;
// 世界画布取 1200×660（约 1.82:1）以贴合实际画布（宽 100% × 高 70vh ≈ 1.85:1）：
// 长宽比不匹配时 fitView 只能按短边适配，左右会留下大片空当、整图白白缩小三成。
export const DEFAULT_H = 660;

/** 分配一块布局状态：位置 / 位移缓存 / 已布点标记 */
export function newLayout(nNodes, w = DEFAULT_W, h = DEFAULT_H) {
  return {
    n: nNodes,
    w,
    h,
    pos: new Float32Array(nNodes * 2),
    disp: new Float32Array(nNodes * 2),
    placed: new Uint8Array(nNodes), // 0 未布点，1 已布点
  };
}

/**
 * 把 idxs 依次铺到一个以画布中心为心的圆盘上（向日葵 / 费马螺线排布）。
 *
 * 用圆盘而非圆环作初始态：环状初值会让弱连接节点滞留成一圈「项链」，视觉上像人为
 * 摆出来的；圆盘初值 + 力导向松弛出来的是自然团聚的簇群，没有可用性代价。
 * 顺序仍由调用方按科年给出 —— 于是螺线由内向外即年代由早到晚，
 * 年代相近者先天相邻，同名科、同地域的小团簇会自己长出来。
 * 排布完全由下标决定（不掷随机数），同一份数据每次都是同一张图。
 */
export function placeDisc(L, idxs, radius) {
  const cx = L.w / 2;
  const cy = L.h / 2;
  const n = Math.max(idxs.length, 1);
  const GOLDEN = 2.399963229728653;
  for (let i = 0; i < idxs.length; i++) {
    const r = radius * Math.sqrt((i + 0.5) / n);
    const a = i * GOLDEN;
    const v = idxs[i] * 2;
    L.pos[v] = cx + Math.cos(a) * r;
    L.pos[v + 1] = cy + Math.sin(a) * r * 0.82; // 压扁，贴合 1200×840 的横长画布
    L.placed[idxs[i]] = 1;
  }
}

/** 把 idxs 依次排到以 (cx,cy) 为心的圆环上（保留：需要严格的年代环时可用） */
export function placeRing(L, idxs, radius) {
  const cx = L.w / 2;
  const cy = L.h / 2;
  const n = idxs.length;
  for (let i = 0; i < n; i++) {
    const a = (i / Math.max(n, 1)) * Math.PI * 2 - Math.PI / 2;
    const v = idxs[i] * 2;
    L.pos[v] = cx + Math.cos(a) * radius;
    L.pos[v + 1] = cy + Math.sin(a) * radius * 0.82; // 压扁，贴合 1200×840 的横长画布
    L.placed[idxs[i]] = 1;
  }
}

/**
 * 把 idx 放到 refs（邻居）的质心；refs 全未布点时退化为画布中心。
 * jitterSeed 只用于同批多点共位的确定性错开，不引入随机。
 */
export function placeCentroid(L, idx, refs, jitterSeed = 0) {
  const cx = L.w / 2;
  const cy = L.h / 2;
  let sx = 0;
  let sy = 0;
  let c = 0;
  for (const r of refs) {
    if (!L.placed[r]) continue;
    sx += L.pos[r * 2];
    sy += L.pos[r * 2 + 1];
    c++;
  }
  const v = idx * 2;
  if (c) {
    L.pos[v] = sx / c;
    L.pos[v + 1] = sy / c;
  } else {
    L.pos[v] = cx;
    L.pos[v + 1] = cy;
  }
  if (jitterSeed) {
    // 确定性抖动：同批节点共位会因斥力奇异而弹飞，先错开一点点
    const h = (jitterSeed * 2654435761) >>> 0;
    L.pos[v] += ((h % 97) / 97 - 0.5) * 24;
    L.pos[v + 1] += (((h >>> 9) % 89) / 89 - 0.5) * 24;
  }
  L.placed[idx] = 1;
}

/**
 * 迭代求解。
 * @param {object} L        newLayout() 的返回值
 * @param {number[]} active 参与本轮布局的节点下标（其余节点视为空气）
 * @param {Array<[number,number]>} edges 边（下标对）
 * @param {number} iters    迭代次数
 * @param {object} [opt]    { t0 初始步长比(×k) · rep 斥力系数 · grav 向心系数 }
 * @returns {{ms:number, k:number}} 耗时与理想边长
 */
export function relax(L, active, edges, iters, opt = {}) {
  const t1 = now();
  const n = active.length;
  if (n === 0 || iters <= 0) return { ms: 0, k: 0 };

  const t0Ratio = opt.t0 ?? 0.5;
  // 斥力必须按节点数归一，否则节点越多、朝外推得越狠，整图会被顶到画布边框上
  const rep = (opt.rep ?? 5) / n;
  const gravity = opt.grav ?? 0.8;

  const P = L.pos;
  const D = L.disp;
  const k = Math.sqrt((L.w * L.h) / n);
  const k2 = k * k;
  const t0 = k * t0Ratio;
  const cx = L.w / 2;
  const cy = L.h / 2;
  const pad = 10;
  const maxX = L.w - pad;
  const maxY = L.h - pad;
  const gravX = gravity * k / (L.w / 2); // 归一化：中心距达半宽时 ≈ gravity·k
  const gravY = gravity * k / (L.h / 2);

  for (let it = 0; it < iters; it++) {
    for (let i = 0; i < n; i++) {
      const v = active[i] * 2;
      D[v] = 0;
      D[v + 1] = 0;
    }

    // 斥力：靠得很近时改用确定性散开方向，避免 d→0 时除零炸飞
    for (let i = 0; i < n; i++) {
      const vi = active[i] * 2;
      const xi = P[vi];
      const yi = P[vi + 1];
      for (let j = i + 1; j < n; j++) {
        const vj = active[j] * 2;
        let dx = xi - P[vj];
        let dy = yi - P[vj + 1];
        let d2 = dx * dx + dy * dy;
        if (d2 < 0.01) {
          dx = ((i * 37 + j * 11) % 13) - 6 || 1;
          dy = ((i * 17 + j * 29) % 13) - 6 || -1;
          d2 = dx * dx + dy * dy;
        }
        const f = (k2 * rep) / d2; // 位移 = f·(dx,dy)，等价于沿单位向量的 k²/d
        D[vi] += dx * f;
        D[vi + 1] += dy * f;
        D[vj] -= dx * f;
        D[vj + 1] -= dy * f;
      }
    }

    // 引力
    for (let e = 0; e < edges.length; e++) {
      const va = edges[e][0] * 2;
      const vb = edges[e][1] * 2;
      const dx = P[va] - P[vb];
      const dy = P[va + 1] - P[vb + 1];
      const d = Math.sqrt(dx * dx + dy * dy) || 1e-4;
      const f = d / k; // 位移 = f·(dx,dy)，等价于沿单位向量的 d²/k
      D[va] -= dx * f;
      D[va + 1] -= dy * f;
      D[vb] += dx * f;
      D[vb + 1] += dy * f;
    }

    // 向心 + 限步 + 越界软回弹
    const cool = Math.pow(1 - it / iters, 1.5);
    const t = t0 * cool + 0.05;
    for (let i = 0; i < n; i++) {
      const v = active[i] * 2;
      let dx = D[v] - (P[v] - cx) * gravX;
      let dy = D[v + 1] - (P[v + 1] - cy) * gravY;
      if (dx > t) dx = t;
      else if (dx < -t) dx = -t;
      if (dy > t) dy = t;
      else if (dy < -t) dy = -t;
      let x = P[v] + dx;
      let y = P[v + 1] + dy;
      if (x < pad) x = pad + (pad - x) * 0.5;
      else if (x > maxX) x = maxX - (x - maxX) * 0.5;
      if (y < pad) y = pad + (pad - y) * 0.5;
      else if (y > maxY) y = maxY - (y - maxY) * 0.5;
      P[v] = x;
      P[v + 1] = y;
    }
  }
  return { ms: now() - t1, k };
}

/**
 * 收尾去重叠。
 *
 * 节点半径是「屏幕像素」（不随缩放变化，保证缩小时仍看得见），而这里是世界坐标，
 * 两者必须换算后才能比较，否则会出现「算着重叠为 0、画出来却黏在一起」。
 * 因此这里接受 radius(i)（屏幕半径）与 scale（当前缩放），
 * 在**世界坐标**下要求 距离 ≥（半径a + 半径b + gap）/ scale。
 *
 * @param {object} L     newLayout() 的返回值
 * @param {number[]} active 活跃节点下标
 * @param {object} opt   { radius(i)→屏幕半径 · scale 当前缩放 · gap 间隙像素 · passes }
 */
export function separate(L, active, opt = {}) {
  const P = L.pos;
  const n = active.length;
  if (!n) return;
  const pad = 10;
  const gap = opt.gap ?? 4;
  const scale = Math.max(0.08, opt.scale ?? 1);
  const rad = opt.radius || (() => 4);
  const r = active.map((i) => rad(i));
  const passes = opt.passes ?? 16;

  for (let it = 0; it < passes; it++) {
    let moved = 0;
    for (let i = 0; i < n; i++) {
      const vi = active[i] * 2;
      const xi = P[vi];
      const yi = P[vi + 1];
      for (let j = i + 1; j < n; j++) {
        const vj = active[j] * 2;
        let dx = P[vj] - xi;
        let dy = P[vj + 1] - yi;
        let d = Math.sqrt(dx * dx + dy * dy);
        const minD = (r[i] + r[j] + gap) / scale;
        if (d >= minD) continue;
        if (d < 1e-3) {
          dx = ((i * 37 + j * 11) % 13) - 6 || 1;
          dy = ((i * 17 + j * 29) % 13) - 6 || -1;
          d = Math.sqrt(dx * dx + dy * dy);
        }
        const push = ((minD - d) * 0.5) / d;
        P[vi] -= dx * push;
        P[vi + 1] -= dy * push;
        P[vj] += dx * push;
        P[vj + 1] += dy * push;
        moved++;
      }
    }
    if (!moved) break;
  }
  for (let i = 0; i < n; i++) {
    const v = active[i] * 2;
    if (P[v] < pad) P[v] = pad;
    else if (P[v] > L.w - pad) P[v] = L.w - pad;
    if (P[v + 1] < pad) P[v + 1] = pad;
    else if (P[v + 1] > L.h - pad) P[v + 1] = L.h - pad;
  }
}

/** 活跃节点的包围盒（供页面 fitView 用） */export function bounds(L, active) {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const i of active) {
    const x = L.pos[i * 2];
    const y = L.pos[i * 2 + 1];
    if (x < x0) x0 = x;
    if (y < y0) y0 = y;
    if (x > x1) x1 = x;
    if (y > y1) y1 = y;
  }
  if (x0 === Infinity) return { x0: 0, y0: 0, x1: L.w, y1: L.h };
  return { x0, y0, x1, y1 };
}

// 浏览器与 Node 都能取到的高精度时钟
function now() {
  return typeof performance !== 'undefined' && performance.now
    ? performance.now()
    : Number(process.hrtime.bigint() / 1000n) / 1000;
}
