import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";

interface RealisticEarthProps {
  size?: number | string;
  className?: string;
  ambient?: boolean;
  interactive?: boolean;
  status?: "ready" | "loading" | "degraded";
  onSelectRegion?: (region: string) => void;
}

/**
 * Procedurally generates a photorealistic 2048x1024 Earth map texture:
 * Includes realistic continental landmasses, biomes (forests, tundras, deserts),
 * polar icecaps, and ocean bathymetry.
 */
function createEarthTexture(): {
  colorMap: THREE.CanvasTexture;
  bumpMap: THREE.CanvasTexture;
  specularMap: THREE.CanvasTexture;
  nightMap: THREE.CanvasTexture;
} {
  const width = 2048;
  const height = 1024;

  // 1. Color Map
  const colorCanvas = document.createElement("canvas");
  colorCanvas.width = width;
  colorCanvas.height = height;
  const ctx = colorCanvas.getContext("2d")!;

  // Deep bathymetric ocean base
  const oceanGrad = ctx.createLinearGradient(0, 0, 0, height);
  oceanGrad.addColorStop(0, "#081324");
  oceanGrad.addColorStop(0.2, "#0a182e");
  oceanGrad.addColorStop(0.5, "#0b1b33");
  oceanGrad.addColorStop(0.8, "#0a182e");
  oceanGrad.addColorStop(1, "#081324");
  ctx.fillStyle = oceanGrad;
  ctx.fillRect(0, 0, width, height);

  // Continental Landmasses Geo Data (Key Polygons in Equirectangular projection)
  const CONTINENTS: [number, number][][] = [
    // North America
    [[-168, 65], [-160, 71], [-140, 69], [-120, 75], [-95, 74], [-80, 68], [-60, 60], [-55, 48], [-65, 44], [-75, 38], [-80, 25], [-90, 21], [-105, 23], [-115, 30], [-124, 40], [-125, 49], [-140, 58], [-160, 56], [-168, 65]],
    // Greenland
    [[-55, 83], [-20, 83], [-22, 70], [-42, 60], [-52, 65], [-55, 83]],
    // South America
    [[-75, 10], [-60, 10], [-50, 0], [-35, -5], [-37, -15], [-45, -23], [-55, -35], [-65, -50], [-74, -54], [-75, -45], [-72, -30], [-80, -10], [-80, 0], [-75, 10]],
    // Europe
    [[-10, 36], [0, 42], [5, 43], [10, 44], [15, 40], [25, 38], [28, 41], [30, 46], [22, 55], [10, 54], [5, 50], [-5, 48], [-8, 44], [-10, 36]],
    // Scandinavia
    [[5, 58], [15, 56], [25, 60], [30, 70], [20, 71], [10, 64], [5, 58]],
    // Africa
    [[-17, 15], [-17, 25], [-6, 36], [10, 37], [25, 32], [35, 30], [43, 12], [51, 12], [45, 0], [40, -15], [32, -30], [20, -35], [18, -34], [12, -15], [8, 4], [0, 6], [-10, 5], [-17, 15]],
    // Asia & Siberia
    [[35, 32], [45, 40], [50, 42], [60, 55], [70, 72], [100, 77], [130, 72], [170, 66], [175, 60], [160, 52], [140, 50], [130, 42], [120, 38], [122, 30], [110, 20], [105, 10], [100, 15], [90, 22], [80, 28], [70, 24], [60, 25], [50, 30], [35, 32]],
    // India
    [[70, 24], [80, 28], [88, 22], [80, 10], [77, 8], [73, 16], [70, 24]],
    // Southeast Asia
    [[98, 8], [105, 10], [108, 14], [105, 20], [100, 18], [98, 8]],
    // Australia
    [[113, -22], [120, -15], [135, -12], [142, -11], [148, -20], [153, -28], [150, -37], [138, -35], [130, -32], [115, -34], [113, -22]],
    // Antarctica
    [[-180, -78], [-120, -74], [-60, -65], [0, -70], [60, -66], [120, -66], [180, -78], [180, -90], [-180, -90]],
  ];

  function toScreen(lon: number, lat: number): [number, number] {
    const x = ((lon + 180) / 360) * width;
    const y = ((90 - lat) / 180) * height;
    return [x, y];
  }

  // Draw landmasses with biome gradients
  for (const poly of CONTINENTS) {
    ctx.beginPath();
    let isFirst = true;
    for (const [lon, lat] of poly) {
      const [x, y] = toScreen(lon, lat);
      if (isFirst) {
        ctx.moveTo(x, y);
        isFirst = false;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.closePath();

    // Biome coloring based on average latitude
    const avgLat = poly.reduce((acc, curr) => acc + curr[1], 0) / poly.length;
    let landGrad = ctx.createLinearGradient(0, 0, 0, height);
    if (avgLat < -60 || avgLat > 70) {
      // Polar Ice
      landGrad.addColorStop(0, "#e2e8f0");
      landGrad.addColorStop(1, "#cbd5e1");
    } else if (avgLat >= 10 && avgLat <= 35) {
      // Arid / Desert
      landGrad.addColorStop(0, "#2c2f26");
      landGrad.addColorStop(0.5, "#3d3929");
      landGrad.addColorStop(1, "#282a20");
    } else {
      // Temperate / Forest
      landGrad.addColorStop(0, "#1d291e");
      landGrad.addColorStop(0.5, "#253627");
      landGrad.addColorStop(1, "#172318");
    }
    ctx.fillStyle = landGrad;
    ctx.fill();

    // Subtle continental coastal rim
    ctx.strokeStyle = "rgba(148, 163, 184, 0.22)";
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }

  // Polar Ice Caps
  ctx.fillStyle = "rgba(241, 245, 249, 0.88)";
  // North Pole
  ctx.fillRect(0, 0, width, height * 0.08);
  // South Pole
  ctx.fillRect(0, height * 0.90, width, height * 0.10);

  // 2. Night City Lights Canvas
  const nightCanvas = document.createElement("canvas");
  nightCanvas.width = width;
  nightCanvas.height = height;
  const nCtx = nightCanvas.getContext("2d")!;
  nCtx.fillStyle = "#000000";
  nCtx.fillRect(0, 0, width, height);

  const CITIES: [number, number, number][] = [
    // [lon, lat, intensity]
    [-74, 40.7, 3], [-118, 34, 3], [-87.6, 41.8, 2.5], [-122.4, 37.7, 2.5],
    [-0.1, 51.5, 3], [2.3, 48.8, 3], [13.4, 52.5, 2.5], [37.6, 55.7, 2.5],
    [139.7, 35.6, 3.5], [121.5, 31.2, 3], [116.4, 39.9, 3], [126.9, 37.5, 3],
    [72.8, 19.0, 3], [77.2, 28.6, 3], [55.3, 25.2, 2.5], [31.2, 30.0, 2.5],
    [151.2, -33.8, 2.5], [144.9, -37.8, 2.5], [-43.2, -22.9, 2.5], [-46.6, -23.5, 3],
    [3.3, 6.5, 2], [18.4, -33.9, 2], [28.0, -26.2, 2]
  ];

  for (const [lon, lat, intensity] of CITIES) {
    const [x, y] = toScreen(lon, lat);
    const rad = nCtx.createRadialGradient(x, y, 0, x, y, intensity * 3.5);
    rad.addColorStop(0, "rgba(255, 235, 175, 0.95)");
    rad.addColorStop(0.3, "rgba(255, 190, 90, 0.55)");
    rad.addColorStop(1, "rgba(255, 180, 50, 0)");
    nCtx.fillStyle = rad;
    nCtx.beginPath();
    nCtx.arc(x, y, intensity * 3.5, 0, Math.PI * 2);
    nCtx.fill();
  }

  // 3. Bump Map (Topography)
  const bumpCanvas = document.createElement("canvas");
  bumpCanvas.width = width;
  bumpCanvas.height = height;
  const bCtx = bumpCanvas.getContext("2d")!;
  bCtx.fillStyle = "#000000";
  bCtx.fillRect(0, 0, width, height);
  bCtx.fillStyle = "#555555";
  for (const poly of CONTINENTS) {
    bCtx.beginPath();
    let isFirst = true;
    for (const [lon, lat] of poly) {
      const [x, y] = toScreen(lon, lat);
      if (isFirst) {
        bCtx.moveTo(x, y);
        isFirst = false;
      } else {
        bCtx.lineTo(x, y);
      }
    }
    bCtx.closePath();
    bCtx.fill();
  }

  // 4. Specular Map (Ocean is high specularity / Land is zero)
  const specCanvas = document.createElement("canvas");
  specCanvas.width = width;
  specCanvas.height = height;
  const sCtx = specCanvas.getContext("2d")!;
  sCtx.fillStyle = "#ffffff"; // Oceans reflect
  sCtx.fillRect(0, 0, width, height);
  sCtx.fillStyle = "#000000"; // Land absorbs
  for (const poly of CONTINENTS) {
    sCtx.beginPath();
    let isFirst = true;
    for (const [lon, lat] of poly) {
      const [x, y] = toScreen(lon, lat);
      if (isFirst) {
        sCtx.moveTo(x, y);
        isFirst = false;
      } else {
        sCtx.lineTo(x, y);
      }
    }
    sCtx.closePath();
    sCtx.fill();
  }

  return {
    colorMap: new THREE.CanvasTexture(colorCanvas),
    bumpMap: new THREE.CanvasTexture(bumpCanvas),
    specularMap: new THREE.CanvasTexture(specCanvas),
    nightMap: new THREE.CanvasTexture(nightCanvas),
  };
}

/**
 * Creates atmospheric cloud texture
 */
function createCloudTexture(): THREE.CanvasTexture {
  const width = 1024;
  const height = 512;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "rgba(0, 0, 0, 0)";
  ctx.fillRect(0, 0, width, height);

  // Generate delicate, realistic cloud bands
  for (let i = 0; i < 48; i++) {
    const x = Math.random() * width;
    const y = 80 + Math.random() * (height - 160);
    const radiusX = 40 + Math.random() * 140;
    const radiusY = 12 + Math.random() * 32;
    const rot = (Math.random() - 0.5) * 0.2;

    const grad = ctx.createRadialGradient(x, y, 0, x, y, radiusX);
    grad.addColorStop(0, "rgba(255, 255, 255, 0.42)");
    grad.addColorStop(0.5, "rgba(255, 255, 255, 0.18)");
    grad.addColorStop(1, "rgba(255, 255, 255, 0)");

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(rot);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(0, 0, radiusX, radiusY, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  return new THREE.CanvasTexture(canvas);
}

export function RealisticEarth({
  size = 400,
  className = "",
  ambient = false,
  interactive = true,
  status = "ready",
}: RealisticEarthProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const [webGLFailed, setWebGLFailed] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Check WebGL availability
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      rendererRef.current = renderer;
    } catch {
      setWebGLFailed(true);
      return;
    }

    const width = container.clientWidth || (typeof size === "number" ? size : 380);
    const height = container.clientHeight || width;
    renderer.setSize(width, height);
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 1000);
    camera.position.z = 2.8;

    // Lighting: Sun Directional Light + Subtle Ambient fill
    const sunLight = new THREE.DirectionalLight(0xffffff, 2.2);
    sunLight.position.set(4, 2, 3);
    scene.add(sunLight);

    const ambientLight = new THREE.AmbientLight(0x222630, 0.65);
    scene.add(ambientLight);

    // Planet Earth Sphere
    const textures = createEarthTexture();
    const earthGeo = new THREE.SphereGeometry(1, 64, 64);
    const earthMat = new THREE.MeshPhongMaterial({
      map: textures.colorMap,
      bumpMap: textures.bumpMap,
      bumpScale: 0.04,
      specularMap: textures.specularMap,
      specular: new THREE.Color(0x334466),
      shininess: 24,
      emissiveMap: textures.nightMap,
      emissive: new THREE.Color(0xaaaa88),
      emissiveIntensity: 0.85,
    });
    const earthMesh = new THREE.Mesh(earthGeo, earthMat);
    scene.add(earthMesh);

    // Cloud Layer Sphere (slightly larger for parallax)
    const cloudTexture = createCloudTexture();
    const cloudGeo = new THREE.SphereGeometry(1.012, 64, 64);
    const cloudMat = new THREE.MeshLambertMaterial({
      map: cloudTexture,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending,
    });
    const cloudMesh = new THREE.Mesh(cloudGeo, cloudMat);
    scene.add(cloudMesh);

    // Outer Atmospheric Fresnel Glow Rim
    const atmosGeo = new THREE.SphereGeometry(1.12, 64, 64);
    const atmosMat = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormal;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec3 vNormal;
        void main() {
          float intensity = pow(0.65 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 2.6);
          gl_FragColor = vec4(0.82, 0.88, 0.96, 1.0) * intensity * 0.75;
        }
      `,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true,
    });
    const atmosMesh = new THREE.Mesh(atmosGeo, atmosMat);
    scene.add(atmosMesh);

    // Orbital ring indicator (Restrained metallic titanium/grey)
    const ringGeo = new THREE.RingGeometry(1.32, 1.33, 96);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x94a3b8,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.22,
    });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.rotation.x = Math.PI / 2.5;
    ringMesh.rotation.y = -0.2;
    scene.add(ringMesh);

    // Interactive Drag Controls
    let isDragging = false;
    let prevMouseX = 0;
    let prevMouseY = 0;
    let rotX = 0.2;
    let rotY = 0;
    let velX = 0;
    let velY = 0.0016; // gentle auto-rotation

    const onPointerDown = (e: PointerEvent) => {
      if (!interactive) return;
      isDragging = true;
      prevMouseX = e.clientX;
      prevMouseY = e.clientY;
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging || !interactive) return;
      const deltaX = e.clientX - prevMouseX;
      const deltaY = e.clientY - prevMouseY;
      prevMouseX = e.clientX;
      prevMouseY = e.clientY;
      rotY += deltaX * 0.006;
      rotX = Math.max(-0.6, Math.min(0.6, rotX + deltaY * 0.004));
      velY = deltaX * 0.001;
      velX = deltaY * 0.001;
    };

    const onPointerUp = () => {
      isDragging = false;
    };

    const dom = renderer.domElement;
    dom.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);

    // Animation Loop
    let animId: number;
    let isMounted = true;

    const animate = () => {
      if (!isMounted) return;
      animId = requestAnimationFrame(animate);

      if (!isDragging) {
        rotY += velY;
        rotX += velX;
        // Friction damping
        velY = velY * 0.98 + (ambient ? 0.0008 : 0.0012) * 0.02;
        velX *= 0.95;
      }

      earthMesh.rotation.y = rotY;
      earthMesh.rotation.x = rotX;
      cloudMesh.rotation.y = rotY * 1.06; // Clouds drift slightly faster
      cloudMesh.rotation.x = rotX;

      renderer.render(scene, camera);
    };

    animate();

    const handleResize = () => {
      if (!container || !renderer) return;
      const nw = container.clientWidth || width;
      const nh = container.clientHeight || nw;
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    };

    window.addEventListener("resize", handleResize);

    return () => {
      isMounted = false;
      cancelAnimationFrame(animId);
      dom.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("resize", handleResize);
      renderer.dispose();
      textures.colorMap.dispose();
      textures.bumpMap.dispose();
      textures.specularMap.dispose();
      textures.nightMap.dispose();
      cloudTexture.dispose();
      earthGeo.dispose();
      earthMat.dispose();
      cloudGeo.dispose();
      cloudMat.dispose();
      atmosGeo.dispose();
      atmosMat.dispose();
      ringGeo.dispose();
      ringMat.dispose();
    };
  }, [size, ambient, interactive, status]);

  if (webGLFailed) {
    // Graceful fallback
    return (
      <div
        className={`earth-fallback ${className}`}
        style={{
          width: size,
          maxWidth: "100%",
          aspectRatio: "1 / 1",
          borderRadius: "50%",
          background: "radial-gradient(circle at 35% 35%, #1e293b, #0f172a 70%, #020617)",
          border: "1px solid rgba(255,255,255,0.12)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#94a3b8",
          fontSize: 12,
        }}
      >
        <span>ORBITAL SENSOR FEED</span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`realistic-earth-container ${className}`}
      style={{
        width: typeof size === "number" ? `${size}px` : size,
        maxWidth: "100%",
        aspectRatio: "1 / 1",
        cursor: interactive ? "grab" : "default",
        userSelect: "none",
        touchAction: "none",
      }}
    />
  );
}
