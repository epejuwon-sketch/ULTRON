import React, { useEffect, useRef } from "react";

interface EarthGlobeProps {
  /** Pixel diameter of the globe canvas (scales cleanly with container via CSS). */
  size?: number;
  /** Subtle ambient backdrop mode (slower rotation, non-interactive). */
  ambient?: boolean;
  /** Live system health state reflected subtly in orbital ring telemetry nodes. */
  status?: "ready" | "degraded" | "loading";
  className?: string;
}

/**
 * Simplified yet geographically recognizable world landmass polygons ([lon, lat] degrees)
 * rendered via real-time 3D orthographic spherical projection with solar terminator lighting,
 * bathymetric ocean depth shading, Rayleigh atmospheric limb glow, night-side city lights,
 * and orbital telemetry arcs. Zero external network/CDN dependencies.
 */
const CONTINENTS: [number, number][][] = [
  // North America
  [
    [-168, 65], [-162, 70], [-140, 70], [-125, 71], [-100, 68], [-82, 63],
    [-64, 58], [-55, 50], [-65, 44], [-74, 40], [-81, 30], [-82, 25],
    [-90, 29], [-97, 26], [-97, 19], [-88, 16], [-83, 10], [-78, 8],
    [-85, 11], [-93, 15], [-105, 20], [-110, 24], [-117, 32], [-124, 42],
    [-125, 49], [-135, 57], [-152, 60], [-164, 60],
  ],
  // Greenland
  [
    [-52, 60], [-42, 60], [-22, 70], [-18, 80], [-42, 83], [-60, 79], [-55, 68],
  ],
  // South America
  [
    [-78, 9], [-71, 12], [-61, 10], [-50, 1], [-35, -6], [-38, -14],
    [-42, -23], [-52, -33], [-62, -40], [-67, -54], [-73, -53], [-74, -42],
    [-71, -30], [-71, -18], [-81, -5], [-79, 2],
  ],
  // Europe
  [
    [-9, 37], [-9, 43], [-2, 43], [-5, 48], [2, 51], [8, 54], [10, 57],
    [5, 61], [15, 68], [28, 70], [42, 67], [55, 66], [58, 52], [45, 45],
    [35, 46], [28, 41], [23, 38], [16, 40], [12, 44], [6, 43], [0, 40], [-5, 36],
  ],
  // UK & Ireland
  [
    [-6, 50], [-5, 58], [-1, 58], [1, 51],
  ],
  // Africa
  [
    [-17, 15], [-13, 28], [-6, 36], [10, 37], [25, 32], [33, 31],
    [43, 12], [51, 11], [45, 2], [40, -10], [35, -24], [28, -33],
    [18, -34], [14, -22], [12, -6], [9, 4], [2, 6], [-8, 5], [-16, 11],
  ],
  // Madagascar
  [
    [44, -25], [47, -25], [50, -13], [46, -15],
  ],
  // Asia + Middle East + India + SE Asia
  [
    [36, 37], [42, 41], [52, 40], [60, 52], [68, 70], [90, 74],
    [120, 73], [145, 70], [170, 66], [162, 58], [142, 54], [135, 43],
    [128, 36], [121, 31], [116, 22], [108, 16], [104, 2], [100, 12],
    [95, 18], [88, 22], [80, 10], [76, 8], [70, 22], [62, 25],
    [56, 26], [59, 22], [52, 16], [44, 13], [36, 28],
  ],
  // Japan
  [
    [131, 32], [136, 34], [141, 41], [145, 44], [140, 40], [134, 35],
  ],
  // Indonesia (Sumatra/Java/Borneo simplified)
  [
    [96, 5], [105, -6], [115, -8], [118, -2], [110, 1], [102, -1],
  ],
  // Australia
  [
    [114, -22], [122, -17], [131, -12], [137, -15], [142, -11], [149, -20],
    [153, -28], [149, -37], [140, -38], [131, -32], [120, -34], [114, -28],
  ],
  // New Zealand
  [
    [167, -46], [173, -41], [178, -37], [174, -40], [170, -45],
  ],
  // Antarctica rim
  [
    [-180, -72], [-120, -73], [-60, -65], [0, -70], [60, -68],
    [120, -67], [180, -72], [180, -88], [-180, -88],
  ],
];

/** Key global metropolitan hubs rendered as subtle golden pinpoint lights ONLY on the night hemisphere. */
const CITY_LIGHTS: [number, number][] = [
  [-74.0, 40.7],   // New York
  [-122.4, 37.8],  // San Francisco
  [-87.6, 41.9],   // Chicago
  [-99.1, 19.4],   // Mexico City
  [-46.6, -23.5],  // Sao Paulo
  [-0.1, 51.5],    // London
  [2.3, 48.9],     // Paris
  [13.4, 52.5],    // Berlin
  [3.4, 6.5],      // Lagos
  [31.2, 30.0],    // Cairo
  [28.0, -26.2],   // Johannesburg
  [55.3, 25.2],    // Dubai
  [72.9, 19.1],    // Mumbai
  [77.2, 28.6],    // Delhi
  [103.8, 1.3],    // Singapore
  [114.2, 22.3],   // Hong Kong
  [121.5, 31.2],   // Shanghai
  [139.7, 35.7],   // Tokyo
  [127.0, 37.6],   // Seoul
  [151.2, -33.9],  // Sydney
];

const DEG = Math.PI / 180;

function projectPoint(
  lonDeg: number,
  latDeg: number,
  rotLon: number,
  tiltLat: number
): { x: number; y: number; z: number } {
  const lon = lonDeg * DEG - rotLon;
  const lat = latDeg * DEG;
  const cosLat = Math.cos(lat);
  const sinLat = Math.sin(lat);
  const cosLon = Math.cos(lon);
  const sinLon = Math.sin(lon);

  const x0 = cosLat * sinLon;
  const y0 = sinLat;
  const z0 = cosLat * cosLon;

  const cosT = Math.cos(tiltLat);
  const sinT = Math.sin(tiltLat);
  const y = y0 * cosT - z0 * sinT;
  const z = y0 * sinT + z0 * cosT;
  return { x: x0, y, z };
}

export function EarthGlobe({
  size = 360,
  ambient = false,
  status = "ready",
  className = "",
}: EarthGlobeProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragRef = useRef<{ active: boolean; lastX: number; lastY: number }>({
    active: false,
    lastX: 0,
    lastY: 0,
  });
  const stateRef = useRef<{ rotLon: number; tiltLat: number; velLon: number }>({
    rotLon: 0.25, // Starts looking across Atlantic / Europe / Africa (Lagos-London corridor)
    tiltLat: 0.24,
    velLon: ambient ? 0.0014 : 0.0024,
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;

    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    let rafId = 0;
    let frame = 0;

    // Normalized solar direction vector (sun illuminating front-upper-left hemisphere)
    const sunLen = Math.hypot(-0.62, -0.35, 0.70);
    const sunX = -0.62 / sunLen;
    const sunY = -0.35 / sunLen;
    const sunZ = 0.70 / sunLen;

    const render = () => {
      frame += 1;
      const st = stateRef.current;
      if (!dragRef.current.active && !reducedMotion) {
        st.rotLon += st.velLon;
        // Gently decay manual drag velocity back to calm orbital drift
        const baseVel = ambient ? 0.0014 : 0.0024;
        st.velLon += (baseVel - st.velLon) * 0.03;
      }

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, size, size);

      const cx = size / 2;
      const cy = size / 2;
      const r = size * 0.39;

      // 1. Subtle deep-space Rayleigh atmospheric halo
      const halo = ctx.createRadialGradient(cx, cy, r * 0.92, cx, cy, r * 1.24);
      halo.addColorStop(0, "rgba(56, 189, 248, 0.20)");
      halo.addColorStop(0.45, "rgba(14, 116, 144, 0.08)");
      halo.addColorStop(1, "rgba(5, 7, 11, 0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, r * 1.24, 0, Math.PI * 2);
      ctx.fill();

      // 2. Back half of inclined orbital telemetry ring
      const orbitTilt = 0.36;
      const orbitRx = r * 1.21;
      const orbitRy = r * 0.33;
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-0.24);
      ctx.beginPath();
      ctx.ellipse(0, 0, orbitRx, orbitRy, 0, Math.PI, Math.PI * 2);
      ctx.strokeStyle = "rgba(148, 163, 184, 0.14)";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();

      // 3. Clip inside planetary sphere
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.clip();

      // Ocean bathymetric base gradient (offset toward solar vector for 3D curvature)
      const oceanGrad = ctx.createRadialGradient(
        cx - r * 0.34,
        cy - r * 0.30,
        r * 0.08,
        cx,
        cy,
        r * 1.08
      );
      oceanGrad.addColorStop(0, "#173c63");
      oceanGrad.addColorStop(0.42, "#0d2542");
      oceanGrad.addColorStop(0.78, "#071426");
      oceanGrad.addColorStop(1, "#030812");
      ctx.fillStyle = oceanGrad;
      ctx.fillRect(cx - r, cy - r, r * 2, r * 2);

      // Subtle precision coordinate graticule (parallels & meridians)
      ctx.strokeStyle = "rgba(148, 197, 255, 0.055)";
      ctx.lineWidth = 0.75;
      for (let lat = -60; lat <= 60; lat += 30) {
        ctx.beginPath();
        let started = false;
        for (let lon = -180; lon <= 180; lon += 6) {
          const p = projectPoint(lon, lat, st.rotLon, st.tiltLat);
          if (p.z > 0) {
            const px = cx + p.x * r;
            const py = cy - p.y * r;
            if (!started) {
              ctx.moveTo(px, py);
              started = true;
            } else {
              ctx.lineTo(px, py);
            }
          } else {
            started = false;
          }
        }
        ctx.stroke();
      }
      for (let lon = -180; lon < 180; lon += 30) {
        ctx.beginPath();
        let started = false;
        for (let lat = -84; lat <= 84; lat += 6) {
          const p = projectPoint(lon, lat, st.rotLon, st.tiltLat);
          if (p.z > 0) {
            const px = cx + p.x * r;
            const py = cy - p.y * r;
            if (!started) {
              ctx.moveTo(px, py);
              started = true;
            } else {
              ctx.lineTo(px, py);
            }
          } else {
            started = false;
          }
        }
        ctx.stroke();
      }

      // 4. Render continents with realistic directional illumination
      for (const poly of CONTINENTS) {
        const projected: { x: number; y: number; z: number }[] = [];
        let visibleCount = 0;
        let avgDot = 0;

        for (const [lon, lat] of poly) {
          const p = projectPoint(lon, lat, st.rotLon, st.tiltLat);
          projected.push(p);
          if (p.z > -0.15) {
            visibleCount += 1;
            avgDot += p.x * sunX + -p.y * sunY + p.z * sunZ;
          }
        }
        if (visibleCount < 3) continue;

        ctx.beginPath();
        let moved = false;
        for (let i = 0; i < projected.length; i++) {
          const p = projected[i];
          // Clamp slightly back-facing edge vertices softly to limb to keep continental silhouettes smooth
          let sx = p.x;
          let sy = p.y;
          if (p.z < 0) {
            const mag = Math.hypot(sx, sy) || 1;
            sx /= mag;
            sy /= mag;
          }
          const px = cx + sx * r;
          const py = cy - sy * r;
          if (!moved) {
            ctx.moveTo(px, py);
            moved = true;
          } else {
            ctx.lineTo(px, py);
          }
        }
        ctx.closePath();

        const lit = Math.max(0, Math.min(1, (avgDot / visibleCount + 0.35) * 0.9));
        const red = Math.round(18 + lit * 26);
        const green = Math.round(44 + lit * 48);
        const blue = Math.round(52 + lit * 32);
        ctx.fillStyle = `rgba(${red}, ${green}, ${blue}, 0.92)`;
        ctx.fill();
        ctx.strokeStyle = `rgba(125, 211, 252, ${0.12 + lit * 0.14})`;
        ctx.lineWidth = 0.85;
        ctx.stroke();
      }

      // 5. Night-side orbital city lights (only appear where hemisphere faces away from sun)
      for (const [lon, lat] of CITY_LIGHTS) {
        const p = projectPoint(lon, lat, st.rotLon, st.tiltLat);
        if (p.z <= 0.08) continue;
        const solarDot = p.x * sunX + -p.y * sunY + p.z * sunZ;
        if (solarDot < 0.08) {
          const nightStrength = Math.min(1, (0.08 - solarDot) * 2.4) * Math.min(1, p.z * 2.2);
          const px = cx + p.x * r;
          const py = cy - p.y * r;
          ctx.fillStyle = `rgba(253, 224, 150, ${0.72 * nightStrength})`;
          ctx.beginPath();
          ctx.arc(px, py, 1.35, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // 6. Specular solar ocean sheen + night-side terminator shadow
      const specular = ctx.createRadialGradient(
        cx - r * 0.42,
        cy - r * 0.36,
        0,
        cx - r * 0.42,
        cy - r * 0.36,
        r * 0.65
      );
      specular.addColorStop(0, "rgba(186, 230, 253, 0.14)");
      specular.addColorStop(1, "rgba(186, 230, 253, 0)");
      ctx.fillStyle = specular;
      ctx.fillRect(cx - r, cy - r, r * 2, r * 2);

      const terminator = ctx.createRadialGradient(
        cx + r * 0.52,
        cy + r * 0.34,
        r * 0.12,
        cx + r * 0.38,
        cy + r * 0.22,
        r * 1.15
      );
      terminator.addColorStop(0, "rgba(2, 6, 14, 0.78)");
      terminator.addColorStop(0.55, "rgba(3, 8, 18, 0.40)");
      terminator.addColorStop(1, "rgba(3, 8, 18, 0)");
      ctx.fillStyle = terminator;
      ctx.fillRect(cx - r, cy - r, r * 2, r * 2);

      // Inner atmospheric Fresnel limb highlight
      const rim = ctx.createRadialGradient(cx, cy, r * 0.80, cx, cy, r);
      rim.addColorStop(0, "rgba(56, 189, 248, 0)");
      rim.addColorStop(0.82, "rgba(56, 189, 248, 0.08)");
      rim.addColorStop(1, "rgba(125, 211, 252, 0.36)");
      ctx.fillStyle = rim;
      ctx.fillRect(cx - r, cy - r, r * 2, r * 2);

      ctx.restore(); // End sphere clip

      // Crisp planetary limb outline
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(125, 211, 252, 0.24)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // 7. Front half of inclined orbital telemetry ring + satellite relay dot
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-0.24);
      ctx.beginPath();
      ctx.ellipse(0, 0, orbitRx, orbitRy, 0, 0, Math.PI);
      ctx.strokeStyle = "rgba(125, 211, 252, 0.22)";
      ctx.lineWidth = 1;
      ctx.stroke();

      const satAngle = (frame * (reducedMotion ? 0 : 0.008) + orbitTilt) % (Math.PI * 2);
      const satX = Math.cos(satAngle) * orbitRx;
      const satY = Math.sin(satAngle) * orbitRy;
      if (Math.sin(satAngle) >= -0.15) {
        const satColor =
          status === "degraded" ? "#f59e0b" : status === "loading" ? "#94a3b8" : "#38bdf8";
        ctx.fillStyle = satColor;
        ctx.beginPath();
        ctx.arc(satX, satY, 2.4, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      ctx.restore();

      if (!reducedMotion) {
        rafId = window.requestAnimationFrame(render);
      }
    };

    render();
    return () => {
      if (rafId) window.cancelAnimationFrame(rafId);
    };
  }, [size, ambient, status]);

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (ambient) return;
    dragRef.current = { active: true, lastX: e.clientX, lastY: e.clientY };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (ambient || !dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.lastX;
    const dy = e.clientY - dragRef.current.lastY;
    dragRef.current.lastX = e.clientX;
    dragRef.current.lastY = e.clientY;
    stateRef.current.rotLon -= dx * 0.007;
    stateRef.current.velLon = -dx * 0.0018;
    stateRef.current.tiltLat = Math.max(-0.65, Math.min(0.65, stateRef.current.tiltLat + dy * 0.004));
  };

  const handlePointerUp = () => {
    dragRef.current.active = false;
  };

  return (
    <canvas
      ref={canvasRef}
      id={ambient ? "ultron-earth-ambient" : "ultron-earth-canvas"}
      aria-label="ULTRON OS 2026 interactive orbital Earth globe"
      className={`earth-canvas ${ambient ? "earth-ambient" : "earth-interactive"} ${className}`}
      style={{ width: size, maxWidth: "100%", aspectRatio: "1 / 1" }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
    />
  );
}
