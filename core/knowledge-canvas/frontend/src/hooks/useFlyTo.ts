import { useCallback, useRef } from "react";
import type { ForceGraphMethods } from "react-force-graph-3d";
import * as THREE from "three";

export function useFlyTo() {
  const fgRef = useRef<ForceGraphMethods | null>(null);
  const registerCanvas = useCallback((fg: ForceGraphMethods) => { fgRef.current = fg; }, []);

  const flyToIds = useCallback((ids: string[]) => {
    const fg = fgRef.current;
    if (!fg || ids.length === 0) return;
    const data = (fg as any).graphData();
    const matched = data.nodes.filter((n: any) => ids.includes(n.id));
    if (matched.length === 0) return;

    const centroid = matched.reduce(
      (acc: THREE.Vector3, n: any) =>
        acc.add(new THREE.Vector3(n.x || 0, n.y || 0, n.z || 0)),
      new THREE.Vector3()
    ).divideScalar(matched.length);

    const spread = Math.max(
      ...matched.map((n: any) =>
        new THREE.Vector3(n.x || 0, n.y || 0, n.z || 0).distanceTo(centroid)
      )
    );
    const distance = Math.max(spread * 2.2, 80);
    const cam = fg.camera();
    const dir = new THREE.Vector3().subVectors(cam.position, centroid).normalize();
    if (dir.lengthSq() < 0.01) dir.set(0, 0, 1);
    const target = centroid.clone().addScaledVector(dir, distance);

    fg.cameraPosition(
      { x: target.x, y: target.y, z: target.z },
      { x: centroid.x, y: centroid.y, z: centroid.z },
      1600
    );
  }, []);

  return { registerCanvas, flyToIds };
}
